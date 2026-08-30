# Mission Control layout audit and decision

## Accepted baseline

The published PR #93 head already has a strong health command, an incident-first
AEGIS/Flight Director surface, a shared `truepanel:status` event, semantic status
words, guarded controls, responsive rules, and diagnostics drawers. The DOM also
contains eleven visually competing top-level cards; CPU, memory, cooling, pools,
drive temperatures, and network are split by telemetry source. The inline legacy
dashboard owns one 5-second status refresh and LCD refresh; GLASS COCKPIT adds no
timer, fetch, listener endpoint, backend authority, or invented field.

## Identical deterministic task fixture

The three executable candidates live in `truepanel/glass_cockpit/candidates`.
All use the same attention-state payload: shared cooling degradation, fan 1,210
RPM falling, hottest drive 43°C rising with unknown bay, pool online, verification
pending. Tests exercise eight operator tasks and 320, 360, 390, 430, 760, 1024,
1440, and 1920 CSS pixel widths.

| Candidate | Competing primary elements | Above-fold task facts | Heuristic interaction cost | Decision domains | Result |
|---|---:|---:|---:|---:|---|
| A: conservative refinement | 11 | 5 | 26 | 8 | Rejected: retains fragmentation and long phone path |
| B: domain consolidation | 4 | 8 | 8 | 4 | Selected |
| C: dense glass cockpit | 7 | 8 | 7 | 6 | Rejected: one unit cheaper but 75% more competition |

“Interaction cost” is the deterministic sum of taps and viewport scroll units,
not elapsed human task time. Candidate C's one-unit advantage does not justify
its extra competing instruments.

## Production candidate

Candidate B became a minimal enhancement rather than a page rewrite:

- a single situation strip keeps **Now, Why, Safest Move, Proof** visible;
- cooling and hottest-drive present values gain compact, text-labelled trends;
- storage state and redundancy sit in the same causal decision group;
- missing bay, pool, redundancy, or history remains `unknown`/`unavailable`;
- secondary evidence stays in a native details element;
- the established AEGIS Flight Director, controls, and IDs remain intact;
- the shared status event is the only data input; there is no recurring poll;
- semantic focus, reduced motion, text alternatives, 44px disclosure targets,
  single-column phone reflow, and overflow-safe content are explicit.

The current-value tiles remain the right representation for CPU and memory. Small
sparklines are appropriate for cooling and drive direction. Full timeline and
forecast graphs remain in Flight Director only where trajectory changes the
decision. Giant catch-all cards and drawer-hidden safety state were rejected.
