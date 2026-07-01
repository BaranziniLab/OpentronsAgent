---
name: opentrons-lab-automation
description: Use OpentronsAgent for Opentrons lab automation workflows. Applies when requests mention Opentrons lab automation protocols robots, or when a user needs guarded API/tool access, provenance review, or integration planning for this platform.
license: Apache-2.0
user-invocable: true
---

Use OpentronsAgent as a BioRouter extension, not as an instruction to fabricate access. Start with `get_opentronsagent_status`, then list targets with `list_opentronsagent_api_targets` before calling APIs or planning commands.

Rules:
- Prefer read-only API methods and metadata discovery first.
- Do not run mutation-capable HTTP methods unless the user explicitly approves the endpoint, method, payload, and side effects, then pass `allow_mutation=true`.
- Do not run local commands unless the exact command, arguments, working directory, and side effects are approved, then pass `allow_execute=true`.
- Preserve provenance fields such as identifiers, versions, URLs, accessions, collection ids, run ids, item ids, and timestamps.
- Treat credentials and tokens as secrets. Never print them in logs or summaries.
