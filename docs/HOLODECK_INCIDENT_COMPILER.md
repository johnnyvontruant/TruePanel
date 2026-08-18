# HoloDeck Incident Compiler

The Incident Compiler converts a privacy-safe Black Box replay into a minimal,
deterministic regression artifact. It does not generate or execute Python,
shell commands, hardware operations, or any other executable code.

## Contract

The compiler accepts a `BlackBoxReplay`, `BlackBoxRecorder`, or recording path
and an injected evaluator. The evaluator receives an ordered sequence of
defensive frame copies and returns `True` while the target invariant violation
is reproduced.

Compilation proceeds in two stages:

1. Find the earliest shortest contiguous time window that still fails.
2. Delta-debug removable frames inside that window while preserving order.

The result contains YAML-ready scenario data and a regression manifest. The
manifest identifies the invariant, retained source sequences, minimized time
span, evaluation budget, budget-exhaustion state, and a SHA-256 digest of the
canonical scenario. Output accessors return defensive copies.

## Safety and bounds

- Black Box frame validation and sanitization remain mandatory.
- The evaluator cannot mutate the replay or subsequent candidates.
- File-backed inputs are bounded before materialization at 10,000 nonblank
  frames, 64 MiB total input, and 256 KiB per frame.
- `max_frames` may lower the 10,000-frame ceiling but cannot raise it.
- `max_evaluations` bounds minimization work and is reported in the manifest.
- Budget exhaustion returns the smallest confirmed candidate found so far.
- Artifacts contain data only and explicitly report that no executable code
  was generated.
- Rejected input is processed before output-directory creation, leaving no
  partial regression artifact.

The evaluator is a seam, not embedded policy. A future layer can connect real
HoloDeck safety invariants, Mission Events, or Health Intelligence outcomes
without coupling the compiler to hardware or production runtime providers.
