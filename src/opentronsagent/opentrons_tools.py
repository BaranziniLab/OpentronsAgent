"""OpentronsAgent's typed tools on the opentrons package (Apache-2.0): protocol simulation and the
labware definitions that ship with it.

opentrons_simulate runs a Flex protocol through opentrons.simulate in this process, which executes
the protocol's Python. So the source must pass protocol_check first, the run is limited in time
and in executed protocol lines, the protocol's own output is captured instead of reaching the MCP
stream, and the tool is not marked read only, so Biorouter asks the person before each run.
Opentrons keeps its configuration under OT_API_CONFIG_DIR, which this module points at the
extension's own data folder before opentrons is first imported.
"""

import contextlib
import io
import json
import os
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from mcp.types import TextContent, ToolAnnotations
from pydantic import Field

from . import protocol_check

PROTOCOL_FILE = "opentronsagent-protocol.py"
MAX_LINES_EXECUTED = 2_000_000
MAX_SECONDS = 60.0
MAX_LOG_LINES = 400
MAX_CUSTOM_LABWARE = 20
_run_lock = threading.Lock()


def data_dir() -> Path:
    configured = (os.getenv("OPENTRONS_DATA_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser()
    root = (os.getenv("BIOROUTER_PATH_ROOT") or "").strip()
    if root:
        return Path(root).expanduser() / "data" / "extension-data" / "opentronsagent"
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "UCSF" / "biorouter" / "data"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "biorouter"
    return base / "extension-data" / "opentronsagent"


def _prepare_environment() -> None:
    folder = data_dir() / "opentrons-config"
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["OT_API_CONFIG_DIR"] = str(folder)


def _result(payload: Any) -> ToolResult:
    return ToolResult(content=[TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False, default=str))])


class BudgetExceeded(Exception):
    pass


def _limited_tracer(deadline: float, max_lines: int):
    counter = {"lines": 0}

    def local(frame, event, arg):
        if event == "line":
            counter["lines"] += 1
            if counter["lines"] > max_lines:
                raise BudgetExceeded(f"the protocol ran more than {max_lines} lines")
            if counter["lines"] % 1000 == 0 and time.monotonic() > deadline:
                raise BudgetExceeded(f"the protocol ran longer than {MAX_SECONDS:.0f} seconds")
        return local

    def global_tracer(frame, event, arg):
        if frame.f_code.co_filename == PROTOCOL_FILE:
            if time.monotonic() > deadline:
                raise BudgetExceeded(f"the protocol ran longer than {MAX_SECONDS:.0f} seconds")
            return local
        return None

    return global_tracer, counter


def _summarise(runlog: list[dict[str, Any]]) -> dict[str, Any]:
    from opentrons.simulate import format_runlog

    text = format_runlog(runlog).splitlines()
    commands: dict[str, int] = {}

    def walk(entries):
        for entry in entries:
            name = ((entry.get("payload") or {}).get("text") or "").split(" ")[0] or "step"
            commands[name] = commands.get(name, 0) + 1
            walk(entry.get("logs") or [])

    walk(runlog)
    return {"steps": len(text), "step_counts": dict(sorted(commands.items(), key=lambda kv: -kv[1])),
            "run_log": text[:MAX_LOG_LINES], "run_log_truncated": len(text) > MAX_LOG_LINES}


def _simulation_error(exc: Exception) -> str:
    """The protocol engine wraps errors in a long repr; keep the first detail line."""
    import re

    text = str(exc)
    budget = re.search(r"BudgetExceeded[^:]*: (the protocol ran [^'\"]+)", text)
    if budget:
        return f"Stopped: {budget.group(1)}."
    detail = re.search(r"detail='([^']{1,1500})'", text) or re.search(r'detail="([^"]{1,1500})"', text)
    if detail:
        return f"{type(exc).__name__}: {detail.group(1)}"
    return f"{type(exc).__name__}: {text[:1500]}"


def simulate_protocol(source: str, custom_labware: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    protocol_check.check(source, PROTOCOL_FILE)
    if custom_labware and len(custom_labware) > MAX_CUSTOM_LABWARE:
        raise ToolError(f"At most {MAX_CUSTOM_LABWARE} custom labware definitions per call.")
    _prepare_environment()
    from opentrons.simulate import simulate

    labware_dir = None
    if custom_labware:
        import tempfile

        labware_dir = tempfile.mkdtemp(prefix="custom-labware-", dir=data_dir())
        for index, definition in enumerate(custom_labware):
            if not isinstance(definition, dict) or not isinstance(definition.get("parameters"), dict) or "loadName" not in definition["parameters"]:
                raise ToolError("Each custom labware item is an Opentrons labware definition with parameters.loadName.")
            Path(labware_dir, f"{index}.json").write_text(json.dumps(definition), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    deadline = time.monotonic() + MAX_SECONDS
    tracer, counter = _limited_tracer(deadline, MAX_LINES_EXECUTED)
    started = time.monotonic()
    error: Optional[str] = None
    runlog: list[dict[str, Any]] = []
    with _run_lock, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        threading.settrace_all_threads(tracer)
        sys.settrace(tracer)
        try:
            runlog, _bundle = simulate(io.StringIO(source), file_name=PROTOCOL_FILE,
                                       custom_labware_paths=[labware_dir] if labware_dir else None)
        except BudgetExceeded as exc:
            error = f"Stopped: {exc}."
        except Exception as exc:  # a failed simulation is a result, not a tool error
            error = _simulation_error(exc)
        finally:
            sys.settrace(None)
            threading.settrace_all_threads(None)
            if labware_dir:
                import shutil

                shutil.rmtree(labware_dir, ignore_errors=True)
    payload: dict[str, Any] = {"ok": error is None, "seconds": round(time.monotonic() - started, 2),
                               "protocol_lines_executed": counter["lines"]}
    if error:
        payload["error"] = error
    if runlog:
        payload.update(_summarise(runlog))
    printed = out.getvalue()
    if printed:
        payload["protocol_output"] = printed[-4000:]
    return payload


@lru_cache(maxsize=1)
def labware_index() -> list[dict[str, Any]]:
    from importlib import resources

    root = resources.files("opentrons_shared_data") / "data" / "labware" / "definitions" / "2"
    rows = []
    for folder in sorted(root.iterdir(), key=lambda p: p.name):
        if not folder.is_dir():
            continue
        versions = sorted((int(f.name.split(".")[0]) for f in folder.iterdir() if f.name.endswith(".json") and f.name.split(".")[0].isdigit()))
        if not versions:
            continue
        definition = json.loads((folder / f"{versions[-1]}.json").read_text(encoding="utf-8"))
        meta = definition.get("metadata", {})
        rows.append({"load_name": folder.name, "display_name": meta.get("displayName"), "category": meta.get("displayCategory"),
                     "brand": (definition.get("brand") or {}).get("brand"), "versions": versions, "wells": len(definition.get("wells", {}))})
    return rows


def labware_definition(load_name: str, version: Optional[int] = None) -> dict[str, Any]:
    from importlib import resources

    match = next((r for r in labware_index() if r["load_name"] == load_name), None)
    if match is None:
        raise ToolError(f"No labware is named {load_name!r}. Use opentrons_labware_search.")
    version = version or match["versions"][-1]
    if version not in match["versions"]:
        raise ToolError(f"{load_name} has versions {match['versions']}.")
    path = resources.files("opentrons_shared_data") / "data" / "labware" / "definitions" / "2" / load_name / f"{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def register(mcp: FastMCP) -> None:
    def opentrons_simulate(
        protocol: str = Field(max_length=protocol_check.MAX_SOURCE_BYTES, description="The protocol's Python source (Python API, robotType Flex)."),
        custom_labware: Optional[list[dict[str, Any]]] = Field(default=None, description="Custom labware definitions (JSON) the protocol loads, if any."),
    ) -> ToolResult:
        try:
            payload = simulate_protocol(protocol, custom_labware)
        except protocol_check.ProtocolRejected as exc:
            raise ToolError(str(exc)) from None
        return _result(payload)

    mcp.tool(
        opentrons_simulate,
        name="opentrons_simulate",
        description=(
            "Simulate an Opentrons Flex protocol with the opentrons package and return the run log, step counts and any error "
            "(for example a pipette asked to hold more than its volume, or labware in a slot that cannot hold it). This runs "
            "the protocol's Python on this computer, so Biorouter asks before each run. Only the Opentrons API and a few "
            "standard modules may be used, and a run stops after 60 seconds. Opentrons 10 simulates Flex protocols only."
        ),
        annotations=ToolAnnotations(title="Simulate an Opentrons protocol", readOnlyHint=False, destructiveHint=False,
                                    idempotentHint=True, openWorldHint=False),
    )

    def opentrons_labware_search(
        text: str = Field(default="", max_length=100, description="Part of a load name or display name, for example 96 well, reservoir, tiprack."),
        category: Optional[str] = Field(default=None, max_length=40, description="wellPlate, tipRack, reservoir, tubeRack, aluminumBlock, adapter, other."),
        limit: int = Field(default=50, ge=1, le=500),
    ) -> ToolResult:
        needle = text.lower().strip()
        rows = [r for r in labware_index()
                if (not needle or needle in r["load_name"].lower() or needle in (r["display_name"] or "").lower())
                and (not category or r["category"] == category)]
        return _result({"opentrons_shared_data": _shared_data_version(), "matches": len(rows), "labware": rows[:limit]})

    mcp.tool(
        opentrons_labware_search,
        name="opentrons_labware_search",
        description="Search the standard Opentrons labware definitions that ship with the opentrons package, by load name, display name or category. No network call.",
        annotations=ToolAnnotations(title="Search Opentrons labware", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )

    def opentrons_labware_definition(
        load_name: str = Field(max_length=120, description="A labware load name, for example corning_96_wellplate_360ul_flat."),
        version: Optional[int] = Field(default=None, ge=1, le=100, description="Definition version; the newest by default."),
        include_wells: bool = Field(default=False, description="Include every well's geometry (large)."),
    ) -> ToolResult:
        definition = labware_definition(load_name, version)
        wells = definition.get("wells", {})
        first = next(iter(wells.values()), {})
        summary = {
            "load_name": load_name, "version": definition.get("version"), "display_name": definition.get("metadata", {}).get("displayName"),
            "category": definition.get("metadata", {}).get("displayCategory"), "brand": definition.get("brand"),
            "dimensions_mm": definition.get("dimensions"), "wells": len(wells), "ordering_columns": len(definition.get("ordering", [])),
            "well_volume_ul": first.get("totalLiquidVolume"), "well_depth_mm": first.get("depth"), "well_shape": first.get("shape"),
            "parameters": definition.get("parameters"), "allowed_roles": definition.get("allowedRoles"),
        }
        if include_wells:
            summary["well_geometry"] = wells
        return _result(summary)

    mcp.tool(
        opentrons_labware_definition,
        name="opentrons_labware_definition",
        description="Show one standard Opentrons labware definition: dimensions, well count, volume, depth and shape, and optionally every well. No network call.",
        annotations=ToolAnnotations(title="Opentrons labware definition", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )


def _shared_data_version() -> Optional[str]:
    try:
        from importlib.metadata import version

        return version("opentrons-shared-data")
    except Exception:
        return None
