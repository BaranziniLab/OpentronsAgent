---
name: opentrons-lab-automation
description: "How to call OpentronsAgent's tools to read Opentrons labware, pipette and deck definitions."
---

# Calling OpentronsAgent

This skill says how to call the OpentronsAgent extension's tools. For the method itself, use the BAAM skill `laboratory-automation-planning`.

## Tools

- `opentrons_status`: shows which targets are configured, their routes and which settings are present. It never shows a value and makes no network call.
- `opentrons_get`: reads from a target. It sends `GET`, or `POST` on routes declared as reads, and is marked read only, so Biorouter's Smart approval runs it without asking.

## Targets

| Target | Base URL | Credential | Reads | Writes |
| --- | --- | --- | --- | --- |
| `shared_data` | `https://raw.githubusercontent.com/Opentrons/opentrons` | none | GET `/*/shared-data/labware/**`, GET `/*/shared-data/pipette/**`, GET `/*/shared-data/deck/**`, GET `/*/shared-data/module/**`, GET `/*/shared-data/liquid-class/**` | none |
| `github` | `https://api.github.com` | none | GET `/repos/Opentrons/opentrons/contents/shared-data/**` | none |

## Rules

- Call `opentrons_status` first. It shows which targets are configured and which
  settings are missing, without showing any value.
- Pass `path` relative to the target's base URL, for example `/edge/shared-data/labware/definitions/2/corning_96_wellplate_360ul_flat/2.json`. Put
  query values in `query`, not in the path.
- A full URL is accepted only on the target's own host. The extension refuses any
  other host, so do not try to reach other services through it.
- Never put a credential in a tool argument. The extension attaches it.
- This extension is read only: it has no write tool.
