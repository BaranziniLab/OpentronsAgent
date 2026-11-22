"""OpentronsAgent: the protocol checks, simulation (a passing Flex protocol, a failing one, a runaway
loop, an OT-2 protocol), captured protocol output over a real stdio server, and the labware tools."""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "flex_transfer.py").read_text()
DATA = tempfile.mkdtemp(prefix="opentronsagent-test-")
os.environ["OPENTRONS_DATA_DIR"] = DATA

from opentronsagent import opentrons_tools as ot  # noqa: E402
from opentronsagent import protocol_check  # noqa: E402

HEADER = 'from opentrons import protocol_api\nrequirements = {"robotType": "Flex", "apiLevel": "2.20"}\n'


class Checks(unittest.TestCase):
    def test_fixture_passes(self):
        protocol_check.check(FIXTURE)

    def test_refusals(self):
        for source in (
            "import os\n",
            "import subprocess\n",
            "from opentrons import _internal\n",
            "from . import x\n",
            "x = open('/etc/passwd').read()\n",
            "x = eval('1')\n",
            "x = ().__class__.__bases__\n",
            "x = '{0.__class__}'.format(1)\n",
            "x = __import__('os')\n",
            "from opentrons import protocol_api\nx = protocol_api.os\n",
            "def run(protocol):\n    global y\n",
        ):
            with self.assertRaises(protocol_check.ProtocolRejected, msg=source):
                protocol_check.check(source)

    def test_size_limit(self):
        with self.assertRaises(protocol_check.ProtocolRejected):
            protocol_check.check("#" * (protocol_check.MAX_SOURCE_BYTES + 1))


class Simulation(unittest.TestCase):
    def test_flex_protocol_simulates(self):
        out = ot.simulate_protocol(FIXTURE)
        self.assertTrue(out["ok"], out.get("error"))
        self.assertGreater(out["steps"], 20)
        self.assertTrue(any("Transferring 100.0" in line for line in out["run_log"]))
        self.assertTrue(Path(os.environ["OT_API_CONFIG_DIR"]).is_relative_to(Path(DATA)))

    def test_failing_protocol_is_a_result(self):
        source = FIXTURE.replace("pipette.transfer(100, reservoir", "pipette.pick_up_tip()\n    pipette.aspirate(900, reservoir['A1'])\n    pipette.transfer(100, reservoir")
        out = ot.simulate_protocol(source)
        self.assertFalse(out["ok"])
        self.assertIn("error", out)

    def test_runaway_loop_is_stopped(self):
        source = HEADER + "def run(protocol):\n    n = 0\n    while True:\n        n += 1\n"
        out = ot.simulate_protocol(source)
        self.assertFalse(out["ok"])
        self.assertIn("Stopped", out["error"])
        self.assertLess(out["seconds"], ot.MAX_SECONDS + 5)

    def test_ot2_protocol_is_reported(self):
        source = 'from opentrons import protocol_api\nrequirements = {"robotType": "OT-2", "apiLevel": "2.20"}\ndef run(protocol):\n    pass\n'
        out = ot.simulate_protocol(source)
        self.assertFalse(out["ok"])
        self.assertIn("OT-2", out["error"])

    def test_custom_labware_is_loaded(self):
        definition = ot.labware_definition("corning_96_wellplate_360ul_flat")
        custom = json.loads(json.dumps(definition))
        custom["namespace"] = "custom_beta"
        custom["parameters"]["loadName"] = "lab_custom_plate"
        custom["metadata"]["displayName"] = "Lab custom plate"
        source = FIXTURE.replace('"corning_96_wellplate_360ul_flat", "D2"', '"lab_custom_plate", "D2", namespace="custom_beta"')
        out = ot.simulate_protocol(source, [custom])
        self.assertTrue(out["ok"], out.get("error"))
        self.assertEqual(list(Path(DATA).glob("custom-labware-*")), [])


class StdioServer(unittest.TestCase):
    def test_protocol_print_does_not_reach_the_mcp_stream(self):
        from fastmcp import Client
        from fastmcp.client.transports import StdioTransport

        source = FIXTURE.replace("def run(protocol: protocol_api.ProtocolContext):\n", "def run(protocol: protocol_api.ProtocolContext):\n    print('hello from the protocol')\n")
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT")}
        env["OPENTRONS_DATA_DIR"] = DATA
        transport = StdioTransport(command=sys.executable, args=["-m", "opentronsagent"], env=env, cwd=str(ROOT / "src"))

        async def go():
            async with Client(transport) as client:
                tools = {t.name: t.annotations.model_dump(by_alias=True) for t in await client.list_tools()}
                result = await client.call_tool("opentrons_simulate", {"protocol": source}, raise_on_error=False)
                return tools, result

        tools, result = asyncio.run(go())
        self.assertFalse(result.is_error, result.content[0].text)
        payload = json.loads(result.content[0].text)
        self.assertTrue(payload["ok"])
        self.assertIn("hello from the protocol", payload["protocol_output"])
        self.assertFalse(tools["opentrons_simulate"]["readOnlyHint"])
        self.assertTrue(tools["opentrons_labware_search"]["readOnlyHint"])


class Labware(unittest.TestCase):
    def test_search_and_definition(self):
        rows = [r for r in ot.labware_index() if r["load_name"] == "corning_96_wellplate_360ul_flat"]
        self.assertEqual(rows[0]["wells"], 96)
        d = ot.labware_definition("nest_12_reservoir_15ml")
        self.assertEqual(len(d["wells"]), 12)


if __name__ == "__main__":
    unittest.main()
