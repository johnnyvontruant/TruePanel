# Project WINGMAN

Project WINGMAN is an experimental, local-first advisory layer for TruePanel. Its job is to make trusted TruePanel evidence easier to understand without becoming a new source of truth, a repair authority, or an autonomous operator.

WINGMAN is deliberately narrower than a general chatbot.

> TruePanel detects. AEGIS, Lifeline, SENTINEL, Pathfinder, and other governed subsystems prove. Manuals define procedure. WINGMAN communicates.

## Product question

WINGMAN should graduate only if it reduces operator cognitive load more than it increases host load, maintenance cost, UI complexity, and failure surface.

A technically successful local model is not enough. If WINGMAN mainly compensates for confusing cards, poor naming, or an overgrown cockpit, the correct fix is to simplify TruePanel instead.

## Intended MVP

The first candidate surface is intentionally small and on demand:

1. **Brief me**: summarize the current privacy-safe Mission Control snapshot in concise operator language.
2. **Explain this**: explain a selected card, state, or term using the bounded manual corpus and current status evidence.
3. **What should I check?**: translate current trusted guidance into human-friendly next steps while preserving every HOLD, REVIEW, ambiguity, and identity boundary.

The MVP does not include autonomous repair, background conversation, general internet access, unrestricted filesystem retrieval, long-term chat memory, or periodic model polling.

## Evidence contract

WINGMAN receives only explicitly constructed `GroundingSource` objects. Current source builders are allowlisted and bounded.

Status grounding may use only the privacy-safe Mission Control sections explicitly exposed by `truepanel.wingman.sources`. Unknown provider state and secret-bearing objects are ignored.

Manual grounding may use only allowlisted TruePanel documentation and bounded heading chunks. WINGMAN does not crawl the repository or filesystem.

Source titles and content are untrusted data. Prompt-like text embedded inside a status field or manual excerpt cannot modify WINGMAN policy.

If deterministic retrieval finds no relevant source, the model is not called.

## Authority boundary

WINGMAN always remains advisory.

- `control_authority=false`
- `production_mutation=false`
- no hardware writes
- no TrueNAS mutations
- no service restart authority
- no promotion authority
- no override of AEGIS HOLD or REVIEW
- no guessed bay, device identity, cause, replacement part, SKU, command result, or repair outcome

A response that violates the structured contract, cites an unknown source, changes mode, or claims authority is discarded and returned as HOLD.

WINGMAN output is presentation, not evidence. Downstream reliability logic must never consume model prose as a detector input or proof artifact.

## Retrieval before generation

The experiment begins with deterministic lexical retrieval instead of embeddings.

This is intentional. The current corpus is small, domain-specific, and heavily structured. A lexical baseline is cheap, inspectable, deterministic, and easy to fail closed. Embeddings should be added only if measured retrieval misses justify their memory, packaging, and lifecycle cost.

The provider is called only after retrieval. Remote inference is disabled by default, and the current provider accepts only loopback endpoints unless an operator explicitly opts out of that safety boundary.

## Structured response contract

The model is asked for constrained JSON containing:

- mode and status
- concise summary
- source IDs supporting the summary
- evidence-backed observations
- evidence-backed next steps
- explicit uncertainty
- `control_authority=false`
- `production_mutation=false`

TruePanel validates the result again after generation. Provider-side schema enforcement is helpful but is not trusted as the only safety layer.

## HoloDeck checkride

`truepanel.holodeck.wingman` defines hardware-isolated scenarios for:

- healthy system briefing
- SMART fault troubleshooting
- unknown replacement part
- AEGIS airworthiness HOLD
- card explanation
- source prompt injection

`truepanel.wingman.evaluation` deterministically scores each generated answer for:

- expected citations
- HOLD preservation
- required uncertainty
- false action claims
- authority and mutation boundaries
- successful advisory completion

`development/tools/benchmark_wingman.py` runs the same cases against any compatible local model. A safety failure exits separately from a quality failure so a fluent but unsafe model cannot win on average score.

## Model bake-off

The model is an implementation detail, not the product. Candidates should be evaluated through the same checkride and host telemetry.

Initial small-model candidates include:

- Qwen3.5 0.8B GGUF
- IBM Granite 4.0 1B GGUF
- Gemma 3 1B Instruct GGUF
- SmolLM3 3B GGUF as a larger comparison point
- other current llama.cpp-compatible instruct models when they offer a credible quality-per-resource advantage

Selection must be based on measured behavior on BattleStation, not leaderboard reputation.

For every candidate record:

- WINGMAN safety pass rate
- WINGMAN total pass rate
- per-case latency
- model load time
- resident memory while idle and during inference
- CPU utilization
- CPU temperature and cooling response
- effect on Plex and normal TrueNAS work
- output quality under evidence gaps and prompt injection

A larger model must show a meaningful quality gain to justify its additional host cost.

## Resource policy

WINGMAN must remain optional. TruePanel core monitoring, alerting, LCD operation, Mission Control, and recovery evidence cannot depend on a model process being available.

Preferred runtime behavior:

- inference on demand only
- no model call on ordinary status refresh
- bounded context assembled from existing privacy-safe snapshots
- one local inference request at a time for the MVP
- model runtime isolated from production TruePanel services
- explicit memory and thread limits during evaluation
- graceful deterministic fallback when the model is unavailable

If persistent model residency materially harms NAS workloads, alternatives include unload-after-use, a smaller model, moving inference to another trusted local host, or not shipping the model feature at all.

## UI policy

Do not add a general-purpose chat pane during the experiment.

The preferred first UI is contextual and small:

- one WINGMAN entry point
- a short system brief
- card-local **Explain** actions
- troubleshooting only when trusted guidance exists
- visible source badges
- visible **ADVISORY ONLY** status
- explicit uncertainty rather than confident filler

The feature should make Pilot mode simpler, not turn Pilot mode into another Flight Engineer console.

## Feature-creep review

WINGMAN should not become the mechanism that makes an overcomplicated TruePanel usable.

Before adding a WINGMAN capability, ask:

1. Could clearer copy or a simpler card solve this deterministically?
2. Does the model have evidence that the existing UI does not already present clearly?
3. Does this require a new collector, daemon, index, database, or polling loop?
4. Would removing the model leave core TruePanel fully understandable and operable?
5. Is the added maintenance surface proportionate to the operator value?

If the first answer is yes, prefer the UI fix. If the fourth answer is no, WINGMAN has become too central.

## Graduation gates

WINGMAN remains experimental until all of the following are true:

- static unit and contract tests pass
- HoloDeck safety cases pass deterministically
- at least two credible small models are compared on identical cases
- the selected model achieves 100% safety-gate pass rate in the approved corpus
- grounding failures reliably abstain or HOLD rather than improvise
- host resource measurements are acceptable during realistic NAS workloads
- the UI adds less complexity than it removes
- model absence has zero effect on core TruePanel operation
- no production deployment occurs as part of the experiment itself

A failed graduation is a valid result. The experiment may conclude that deterministic help and better cockpit design are superior to local generation on this hardware.

## Isolated Mission Control prototype

The experiment branch now includes a separate, opt-in cockpit entry point:
`python -m truepanel.wingman.prototype`. This does **not** alter the regular
Mission Control service or enable inference on normal status refresh.

From an experimental checkout with the existing Python environment, run:

```bash
python -m truepanel.wingman.prototype \
  --llama-server /absolute/path/to/llama-server \
  --model /absolute/path/to/granite-4.0-1b-q4_k_s.gguf \
  --docs-root docs
```

The paths above are placeholders, not installation instructions. Use only
a previously obtained and verified local executable and model. No model is
downloaded automatically. A missing file fails before the prototype binds.

The prototype binds only to `127.0.0.1:18787` by default, refuses the
production port `8787`, disables configuration writes, and denies all POST
requests except `/api/v1/wingman/brief`. The full cockpit is visible for
context, but its normal POST controls are **not available in prototype mode**.
For a remote browser, use an explicitly established SSH tunnel rather than
exposing the prototype on the LAN.

A click on **BRIEF ME** uses the privacy-safe current status, starts the
bounded local runtime on demand if the existing resource gate permits it,
returns a validated advisory or a fail-closed unavailable/HOLD result, and
reaps the model process. The normal Mission Control service is not restarted
or replaced. No production deployment is part of this experiment.

The 3 GiB MemAvailable gate is still provisional; the recorded first
BattleStation experiment began around 2.99 GiB and therefore would not pass
the current gate. Do not lower that threshold merely to make a demonstration
work. Reassess with fresh host telemetry under representative workloads.

## Model-free ground school

The experimental checkout now includes `truepanel.wingman.offline.offline_brief`
and `truepanel.wingman.readiness.inference_readiness`. Both are bounded,
read-only functions over explicitly supplied snapshot and host-resource
evidence. They do not import or invoke a language-model provider.

The isolated prototype exposes two GET-only routes:

- `/api/v1/wingman/offline-brief`: a bounded, source-labeled summary of
  recognized storage pool states, AEGIS HOLD/REVIEW, and operator guidance
  HOLD/REVIEW counts. Unsupported, malformed, or missing fields are not
  converted into healthy verdicts. A missing pool record is explicitly
  uncertain.
- `/api/v1/wingman/readiness`: an observational report of the existing
  memory and load policy plus configured local model and executable
  availability. `READY_FOR_RECHECK` is **not** launch authorization; the
  actual runtime repeats its resource gate immediately before spawning.

The readiness report never returns model paths, credentials, or the raw
snapshot. Both endpoints remain confined to the experimental prototype;
normal Mission Control's route table is unchanged. Hardware-isolated tests
cover absent evidence, HOLD/REVIEW preservation, untrusted status strings,
memory pressure, missing model files, and errors reading host resources.
No production deployment or live checkride is implied by a green CI result.

## Current state

WINGMAN remains on an experiment branch. The brief UI, API composition and
isolated prototype entry point are implemented in that branch. No model is
installed as a production dependency and no production service is changed.
The isolated prototype and its tests still require local CI and real-host
validation before any promotion decision.
