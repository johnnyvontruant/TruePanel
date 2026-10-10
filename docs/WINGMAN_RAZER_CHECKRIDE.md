# WINGMAN on the Razer: architecture and Monday checkride

Development proposal, 2026-10-10. No remote inference has been enabled, no
hardware has been tested, and this document is not deployment authorization.

## Finding

Offloading model computation is a useful experiment. Keep TruePanel's collectors,
deterministic instrument brief, retrieval, answer validation, and every hardware
or recovery authority on BattleStation. Give the Razer only the bounded prompt
and selected evidence needed to return a candidate advisory. A model answer is
never new telemetry, verification, or permission to act.

The checkout inspected was `experiment/project-wingman` at
`2c966423154f7bfcb039abcaaaedcef1db36754c` (PR #156). Accepted `main` was
`bf94a2dbe3a4c6d69b62bcd30e873434d3888e05`; it does not contain this provider.
The open AEGIS temperature and signing-kit PRs are separate work and remain
untouched. The general contributor guide starts changes from `develop`; this
provider fix instead intentionally targets its existing experimental branch so
it does not import WINGMAN into production.

The previously reported approximately 2.09 GiB peak model RSS and resource-gate
refusals motivate the experiment; they were not remeasured in this pass. The
Razer is reported to run Windows and have a good battery. GPU model, dedicated
VRAM, usable RAM, driver, thermals, and lid/sleep behavior remain unverified.
The earlier RTX 3080 mention is not hardware evidence or a sizing guarantee.

## Current code and the missing boundary

| Component | Present behavior | Offload requirement |
| --- | --- | --- |
| `wingman/provider.py` | OpenAI-compatible completion; loopback by default; explicit `allow_remote` escape hatch | Preserve endpoint custody and add authenticated transport before any direct remote deployment |
| `wingman/service.py` | Retrieves bounded sources, calls model, validates structured output and citations | Stay on BattleStation; audit actual selected fields before crossing hosts |
| `wingman/runtime_advisory.py` | Starts and reaps a local llama.cpp process around each request | Separate an external-provider lifecycle; do not spawn a NAS model for a Razer request |
| `wingman/readiness.py` | Checks local model/server files and NAS RAM/load | Retain for local mode; external mode needs distinct observations and reason codes |
| Offline cockpit | Instrument brief survives missing models and HOLD | Preserve unchanged when Razer is asleep, busy, disconnected, or invalid |

Changing the endpoint alone does not offload the runtime: the current wrapper
still starts the local process and applies its local file and resource gates.
Conversely, deleting those gates globally would weaken the existing local mode.
An external provider needs a separate, opt-in path with an honest distinction
between NAS request readiness and Razer inference readiness. Remote health is
an observation, not launch permission, operator identity, or model provenance.

## Implemented precursor: direct HTTP transport

The provider now uses its own opener with an empty proxy map and a redirect
handler that refuses redirects. It neither consults the process-global opener
nor inherits environment/system proxies. Redirects return an HTTP error, which
the existing advisory service maps to `MODEL_UNAVAILABLE` without an advisory
or control authority. Even same-host redirects are refused; configure the final
completion URL explicitly.

This addresses routing custody only. It does not pin DNS, authenticate a Razer,
provide TLS or credentials, bound response bytes, or make `allow_remote=True`
safe by itself. There is no external runtime, new endpoint, readiness shortcut,
automatic inference, or UI change in this patch. Explicit opt-in remains required
for a non-loopback URL; the normal runtime factory still sets it to false.

The HTTP tests use synthetic prompts and two local peers to verify successful
direct POST, 301/302/303/307/308 rejection, no redirected peer contact, no proxy
contact, independence from a process-global opener, and fail-closed service
behavior. These are implementation checks, not live Razer or NAS checkrides.

## Proposed first external experiment

Prefer an explicitly authenticated, encrypted connection to a Razer model server
that remains loopback-bound. A separately managed, host-verified tunnel is one
candidate; the tunnel and remote model process would have their own lifecycle,
not be treated as `WingmanLocalRuntime`. Merely pointing at a loopback tunnel
does not establish which remote machine or model is behind it.

Before enabling that path, define the exact permitted peer, authentication,
connection failure, response limits, timeout, and concurrency policy. Keep the
provider's no-redirect/no-ambient-proxy behavior. Do not expose the model server
publicly or grant it NAS, Home Assistant, filesystem, shell, or recovery tools.
Future BattleHouse voice workloads may share GPU capacity, but need measured
admission behavior; do not assume simultaneous OmniVoice and LLM inference fits.

Failure should retain the deterministic instrument brief with visible uncertainty
and existing AEGIS HOLD/REVIEW. It should not silently start a heavy local model
on BattleStation. Ordinary status refresh must issue no model request; an operator
click should cause at most one bounded advisory attempt.

## Monday checkride, 2026-10-12

1. **Inventory first.** On the Razer, capture GPU name, dedicated VRAM, driver,
   usable system RAM, Windows version, and power/lid settings. If `nvidia-smi` is
   already available, this is a read-only starting point:

   ```powershell
   nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
   ```

   Do not install a driver or change operating systems simply because that
   command is unavailable. Use the local hardware inventory first. Keep serials,
   identifiers, addresses, and credentials out of shared reports.
2. **Choose the smallest model baseline.** Start with the same model and cases
   used in the earlier Wingman bake-off to make the comparison meaningful.
   Record exact model artifact, quantization, server build, and context settings.
   Choose larger candidates only after VRAM and measured quality justify them.
3. **Test the Razer locally.** Use an explicit loopback bind and port. Measure
   cold/warm load, memory, VRAM, latency, thermals, and idle behavior. No NAS
   service change is needed to determine whether the laptop can run the model.
4. **Rehearse the external path in isolation.** After the separate external
   lifecycle/transport contract is implemented, send only synthetic HoloDeck
   evidence through it. Re-run healthy, SMART, unknown-part, AEGIS HOLD, and
   prompt-injection cases with exact citation and zero-authority checks.
5. **Exercise failure.** Sleep or disconnect the laptop, stop the server, return
   a redirect or malformed answer, and attempt a second concurrent request.
   Confirm bounded failure, no background retry loop, no local model spawn,
   and no loss of the existing offline brief or HOLD.
6. **Measure the benefit.** Compare the same cases and ordinary NAS workload
   before/after offload. Record actual NAS load/RAM and Razer resource use.
   Hosted CI does not establish that hardware temperatures or workload impact
   are acceptable. Production consideration follows only after that evidence.

## Primary sources inspected

Checked 2026-10-10; these URLs describe upstream behavior, not a pinned binary
installed on either host. Recheck the selected server build before using flags.

- [Python 3.11 urllib.request](https://docs.python.org/3.11/library/urllib.request.html):
  opener construction, inherited proxies, empty proxy maps, and redirect handling.
- [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md):
  completion API, explicit host binding, authentication/TLS options, and health.
  `/health` is documented as public even when an API key is configured, so its
  success alone does not demonstrate authenticated completion access.
- [NVIDIA System Management Interface](https://docs.nvidia.com/deploy/nvidia-smi/index.html):
  selective GPU inventory. Reported VRAM is a capacity observation, not a model
  performance prediction.
