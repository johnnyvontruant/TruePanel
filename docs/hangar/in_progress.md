# HANGAR · In Progress

> Generated from `truepanel/hangar/registry.json`; edit the registry, not this view.

Registry version 2026.09.15.1 · refreshed 2026-09-15 · 2 experiment(s)

## TP-EXP-0015 · CHECKRIDE live storage recovery

A verified SMART incident can be composed into an identity-bound advisory flight plan and later closed by a machine-verifiable repair signature.

- Safety: `READ_ONLY_EVIDENCE`
- Strongest follow-up: Acquire a compatible replacement, then capture the real repair through the same rehearsed verification contract.
- Revisit when: a compatible replacement drive is available; backup and identity can be freshly reconfirmed

## TP-EXP-0029 · WINGMAN grounded local advisory runtime

Preliminary bake-off selected Granite 4.0 1B Q4_K_S for the next phase: 5/6 final quality and 6/6 safety versus Qwen3.5 0.8B at 4/6 quality and 6/6 safety. Granite requires roughly 2 GiB resident memory, so the proposed runtime remains on-demand rather than persistent.

- Safety: `READ_ONLY_EVIDENCE`
- Strongest follow-up: Build and rehearse the bounded on-demand Granite lifecycle wrapper before exposing any WINGMAN control in Mission Control.
- Revisit when: Granite or llama.cpp runtime version changes; BattleStation memory or CPU configuration changes; WINGMAN evidence or structured-output contract changes; a lighter candidate matches or exceeds Granite on the frozen safety and quality corpus
