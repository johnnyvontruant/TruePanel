# TruePanel Development Guide

## Branch policy

### `main`

`main` is the accepted, deployable platform state. Direct development does not occur on `main`.

### Feature and fix branches

Create focused branches from the current accepted base for code, hardware research, documentation, and migrations.

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout -b feature/<name>
```

Stacked work may branch from an unmerged pull request only when the dependency is intentional and documented. Never quietly expand a branch that has been declared a frozen evidence baseline.

### Protected evidence branches

Some experimental branches and pull requests are preserved to keep a known test result reviewable. When a branch is frozen:

- do not add, amend, squash, or force-push commits;
- do not retarget, close, merge, or rewrite its pull request without explicit approval;
- create a separately named follow-up branch;
- state the dependency in the follow-up pull request.

PR #78 and `feature/project-aegis` are the current preserved AEGIS baseline.

## Development workflow

Before editing:

1. inspect current `main`, open pull requests, and relevant experimental branches;
2. identify the exact accepted base;
3. confirm whether the work requires a stacked branch;
4. keep production and physical-hardware authority out of ordinary development.

Before committing:

```bash
python3 -m compileall -q truepanel
python3 -m pytest -q
git diff --check
git status -sb
```

Also run the applicable focused contracts:

- installed-wheel and fresh-environment smoke tests for packaging changes;
- JavaScript syntax and responsive checks for Mission Control changes;
- HoloDeck scenarios for health, recovery, correlation, or safety changes;
- lifecycle tests for install, upgrade, rollback, repair, verify, and uninstall work;
- privacy tests for support bundles, Black Box, recordings, or exported evidence.

Stage files explicitly. Do not use `git add .` in a checkout that may contain captures, firmware, credentials, machine-specific configuration, or local telemetry.

## Repository boundaries

Commit:

- production source;
- automated tests;
- durable documentation;
- deterministic fixtures;
- reproducible laboratory source;
- example plugins;
- safe reference configuration;
- required third-party notices and provenance.

Do not commit:

- extracted firmware;
- compiled probes;
- caches or virtual environments;
- timestamped backups;
- unsanitized hardware captures or logs;
- runtime plugin state;
- local telemetry;
- credentials or secrets;
- support bundles containing user data;
- machine-specific deployment configuration.

## Architecture rules

- Collection does not decide presentation.
- Watchers produce structured events.
- Alert policy owns interruption and lifecycle.
- Unknown evidence remains unknown.
- Statistical drift cannot invent a hard fault.
- Correlation cannot hide contributing alerts.
- Recovery requires fault-specific verification.
- Reliability analysis does not gain control authority.
- Hardware controllers remain lazy and testable.
- Model-specific commands default off.
- Experimental commands remain behind Stargate interlocks.
- HoloDeck and Black Box artifacts remain bounded and sanitized.
- The standalone Host Agent remains dormant until an explicit cutover project.
- The LCD width is always a hard 16-character boundary.
- Mission Control phone usability is a release constraint.

## Recovery documentation contract

A new actionable guidance code is incomplete until it has:

- a declared detector;
- required evidence fields;
- immediate stabilization guidance;
- diagnostic guidance;
- corrective guidance;
- verification guidance;
- a fault-specific machine verifier;
- deterministic regression coverage;
- a passed fault-present-to-recovered rehearsal.

The Recovery Coverage Matrix and CI contract enforce this rule.

## External software and provenance

TruePanel does not follow a “not invented here” policy.

Before building a large subsystem, search for existing software, algorithms, libraries, and architectural patterns that may save verified development time.

Evaluate candidates for:

- capability and platform fit;
- maintenance activity;
- test quality;
- dependency weight;
- security posture;
- license compatibility;
- attribution and notice requirements;
- replacement cost if the dependency disappears.

Reusable external code must have a compatible, unambiguous license. Preserve provenance and required notices, wrap the dependency behind a TruePanel-owned interface, and add tests that make later replacement possible.

Architectural inspiration still requires attribution when appropriate. Do not copy code from an incompatible or unclear source.

## Hardware changes

Before adding a production write:

1. identify the exact controller and model;
2. document the address, register, opcode, or kernel interface;
3. reproduce the command through simulation or recording transport;
4. verify the command on the intended hardware;
5. prove restoration and abort behavior;
6. isolate it behind a narrow controller class;
7. add duplicate suppression where useful;
8. add tests and evidence capture;
9. default it off for portable configurations;
10. document the support and authority boundary.

Do not perform generic I2C scans, random register writes, manual fan sysfs experiments, direct LCD laboratory work while the service owns the controller, or destructive storage operations on production hardware.

## Documentation

User-visible work is incomplete until the relevant README, operating guide, architecture, configuration, lifecycle, changelog, and roadmap material is synchronized.

Documentation must distinguish:

- stable release behavior;
- accepted development work;
- experimental review candidates;
- live-hardware validation status;
- remaining unproven assumptions.

Avoid hard-coded global test counts in evergreen guides. Put point-in-time validation numbers in pull requests, release notes, or the changelog.

## Pull requests

A reviewable pull request should include:

- accepted base commit;
- branch and commit list;
- architecture or behavior summary;
- safety and authority statement;
- focused and full test results;
- GitHub Actions status;
- simulation or hardware evidence;
- failed approaches and remaining risks;
- exact deploy/no-deploy status;
- documentation impact;
- rollback or next-gate instructions.

Draft status is appropriate while a live-hardware gate, calibration campaign, or stacked dependency remains unresolved.

## Release promotion

A promotion candidate requires:

- a clean, reviewable branch;
- synchronized documentation;
- complete focused and full-suite CI;
- installed-wheel smoke coverage;
- applicable HoloDeck rehearsals;
- explicit hardware validation for model-specific behavior;
- privacy and responsive-layout checks where relevant;
- guarded upgrade and rollback evidence;
- an updated changelog;
- a clear stable-versus-experimental boundary;
- explicit approval to merge and deploy.

A passing test suite is necessary evidence, not automatic production authority.
