"""Static checks a protocol must pass before opentrons_simulate runs it.

Simulating an Opentrons protocol executes its Python, in this process. This module refuses
source that reaches past the Opentrons API: imports other than opentrons and a few standard
modules, calls to eval, exec, open and the other escape hatches, and any attribute that starts
with an underscore or names a module. It is a guard against accidents and casual misuse, not a
sandbox; the run itself is also time and step limited (see opentrons_tools.py) and Biorouter
asks the person before each simulation.
"""

import ast

MAX_SOURCE_BYTES = 200_000
ALLOWED_IMPORTS = {
    "opentrons", "opentrons.protocol_api", "opentrons.types",
    "math", "typing", "itertools", "collections", "functools", "string", "statistics", "decimal",
    "fractions", "dataclasses", "enum", "json", "re",
}
FORBIDDEN_NAMES = {
    "__import__", "eval", "exec", "compile", "open", "input", "globals", "locals", "vars", "getattr",
    "setattr", "delattr", "hasattr", "breakpoint", "help", "memoryview", "__builtins__", "exit", "quit",
    "copyright", "credits", "license", "object", "type", "super", "classmethod", "staticmethod", "property",
    "format",
}
FORBIDDEN_ATTRIBUTES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "importlib", "builtins", "ctypes", "pickle",
    "marshal", "io", "threading", "multiprocessing", "asyncio", "signal", "resource", "inspect",
    "f_globals", "f_locals", "f_back", "f_builtins", "f_code", "gi_frame", "gi_code", "cr_frame", "cr_code",
    "ag_frame", "ag_code", "tb_frame", "tb_next", "func_globals", "mro", "load_module", "system", "popen",
    "format", "format_map", "environ", "getenv",
}


class ProtocolRejected(ValueError):
    pass


def check(source: str, filename: str = "protocol.py") -> ast.Module:
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ProtocolRejected(f"The protocol is larger than {MAX_SOURCE_BYTES} bytes.")
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise ProtocolRejected(f"The protocol is not valid Python: line {exc.lineno}: {exc.msg}") from None
    problems: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_IMPORTS:
                    problems.append(f"line {line}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level or module not in ALLOWED_IMPORTS:
                problems.append(f"line {line}: from {'.' * node.level}{module} import ...")
            for alias in node.names:
                if alias.name.startswith("_") or alias.name == "*":
                    problems.append(f"line {line}: import of {alias.name}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f"line {line}: {node.id}")
        elif isinstance(node, ast.Name) and node.id.startswith("__") and node.id not in {"__name__"}:
            problems.append(f"line {line}: {node.id}")
        elif isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRIBUTES):
            problems.append(f"line {line}: attribute .{node.attr}")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            problems.append(f"line {line}: {type(node).__name__.lower()} statement")
    if problems:
        shown = "; ".join(problems[:10]) + (f"; and {len(problems) - 10} more" if len(problems) > 10 else "")
        raise ProtocolRejected(
            "This extension simulates protocols that use only the Opentrons API and a few standard modules "
            f"(math, typing, itertools, collections, functools, string, statistics, json, re). Not allowed: {shown}."
        )
    return tree
