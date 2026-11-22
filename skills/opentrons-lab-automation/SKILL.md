---
name: opentrons-lab-automation
description: "How to call OpentronsAgent's tools: simulate Opentrons Flex protocols, look up labware definitions, and read Opentrons shared data on GitHub."
---

# Calling OpentronsAgent

This skill says how to call the OpentronsAgent extension's tools. For the method itself
(designing a liquid-handling protocol, plate layouts, controls), use the BAAM skill
`laboratory-automation-planning`.

## Tools

- `opentrons_simulate`: runs a protocol written with the Opentrons Python API through the
  opentrons package's simulator and returns the run log, step counts and any error. It runs the
  protocol's Python on this computer, so Biorouter asks the person before each run.
  - Flex protocols only (`requirements = {"robotType": "Flex", "apiLevel": "2.20"}` or later, up
    to 2.31). Opentrons 10 no longer simulates OT-2 protocols; it says so.
  - The protocol may import only `opentrons` (`protocol_api`, `types`) and math, typing,
    itertools, collections, functools, string, statistics, decimal, fractions, dataclasses, enum,
    json and re. No file, network or system access, no `eval` or `exec`, no attributes that
    start with an underscore, no `str.format`. A run stops after 60 seconds or 2 million lines.
  - Pass custom labware definitions (the JSON from the Opentrons Labware Creator) in
    `custom_labware`, and load them with their `namespace`.
  - A simulation that fails (a tip asked to hold more than it can, a slot that cannot take that
    labware, running out of tips) comes back with `ok: false` and the error. Fix the protocol and
    simulate again before anyone runs it on a robot.
- `opentrons_labware_search` and `opentrons_labware_definition`: the standard labware that ships
  with the opentrons package (load names, well counts, volumes, depths, dimensions). No network
  call.
- `opentrons_status` and `opentrons_get` read Opentrons shared data on GitHub: target
  `shared_data` (raw files, for example
  `/edge/shared-data/labware/definitions/2/corning_96_wellplate_360ul_flat/2.json`) and target
  `github` (directory listings, for example `/repos/Opentrons/opentrons/contents/shared-data/labware/definitions/2`
  with `query: {"ref": "edge"}`).

## Rules

- This extension never talks to a robot. A simulation is evidence the protocol is well formed and
  fits its labware, not that it will behave on the deck; a person still runs it in the Opentrons
  App, with a dry run first.
- Keep the protocol's apiLevel, the labware load names and versions, the pipettes and the
  simulator's warnings in any report.
- The extension holds no credential.
