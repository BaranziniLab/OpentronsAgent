# OpentronsAgent

Simulate Opentrons Flex protocols with the opentrons package and look up the labware definitions it ships, plus Opentrons shared data on GitHub. Biorouter asks before each simulation, which runs the protocol's Python. No key needed.

Current version: **0.3.0**

This release adds typed tools on `opentrons` 10.1.0 (Apache-2.0): `opentrons_simulate` (not read only: it runs the protocol's Python in this process after a static check, with a 60 second and 2 million line limit and its output captured; Biorouter asks before each run), `opentrons_labware_search` and `opentrons_labware_definition`. opentrons 10 simulates Flex protocols only. opentrons declares `jsonschema<4.18`, which the MCP SDK cannot use, so `pyproject.toml` overrides it to `jsonschema>=4.20,<5`; the simulation tests run on that version.

This is a Biorouter extension (a `.brxt` bundle) built on the BRXT adapter kit
1.0.1. Install it from BAAM in Biorouter, or from a file:

```bash
biorouter extension install dist/opentronsagent.brxt
```

## Tools

- `opentrons_status`: shows which targets are configured, their routes and which settings are present. It never shows a value and makes no network call.
- `opentrons_get`: reads from a target. It sends `GET`, or `POST` on routes declared as reads, and is marked read only, so Biorouter's Smart approval runs it without asking.

## Targets

| Target | Base URL | Credential | Reads | Writes |
| --- | --- | --- | --- | --- |
| `shared_data` | `https://raw.githubusercontent.com/Opentrons/opentrons` | none | GET `/*/shared-data/labware/**`, GET `/*/shared-data/pipette/**`, GET `/*/shared-data/deck/**`, GET `/*/shared-data/module/**`, GET `/*/shared-data/liquid-class/**` | none |
| `github` | `https://api.github.com` | none | GET `/repos/Opentrons/opentrons/contents/shared-data/**` | none |

## Settings

| Variable | Required | Secret | Purpose |
| --- | --- | --- | --- |
| `OPENTRONS_DATA_DIR` | no | no | Optional folder for the simulator's configuration and temporary custom labware. Default: a folder beside Biorouter's data. |
| `OPENTRONS_LOG_LEVEL` | no | no | Logging level |

## How it protects your credentials

- Each credential is attached only to requests for its own target's host. A full URL
  that names another host, a path starting with `//`, plain `http` and a redirect to
  another host are all refused, so a prompt that names a URL cannot move a key off
  the service it belongs to.
- Reads use `GET`, or `POST` on the routes declared as reads. Writes go through a
  separate tool that Biorouter asks you to approve every time, and only to declared
  routes.
- The extension never runs a local command. Use Biorouter's Developer shell for that.
- Credential values never appear in tool results, error messages or logs.

## Develop and release

```bash
uv sync
uv run python -m unittest discover -s tests -v   # contract tests and leak suite
uv run python scripts/build_brxt.py               # writes dist/opentronsagent.brxt and SHA256SUMS
uv run python scripts/version.py X.Y.Z            # moves every version string together
```

Push a tag `vX.Y.Z` equal to the manifest version to publish a release. The release
workflow refuses any other tag. Do not edit `src/opentronsagent/_kit/` or `tests/kit_testing/`:
they are vendored from the kit in the Biorouter repository
(`scripts/brxt-adapter-kit/`, documented in `docs/extensions/brxt-adapter-kit.md`).

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
