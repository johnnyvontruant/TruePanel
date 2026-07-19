# TruePanel Development Guide

## Branches

### `main`

`main` represents released or explicitly promoted platform state. It should remain deployable and documented.

### `develop`

`develop` is the active integration branch. Completed feature work lands here after tests, cleanup, and documentation.

### Feature branches

Use focused branches for large or hazardous work, especially hardware research, protocol changes, plugins, and migrations.

## Development workflow

```bash
git checkout develop
git pull --ff-only origin develop
git checkout -b feature/<name>
```

Before committing:

```bash
python3 -m compileall -q truepanel
python3 -m pytest -q
git diff --check
git status -sb
```

Stage files explicitly. Do not use `git add .` in a repository containing local captures, firmware, plugins, or hardware experiments.

## Repository boundaries

Commit:

- production source
- automated tests
- durable documentation
- reproducible laboratory source
- example plugins
- reference configuration

Do not commit:

- extracted firmware
- compiled probes
- object files
- caches
- timestamped backups
- hardware captures and logs
- runtime plugin state
- local telemetry
- credentials

## Architecture rules

- Collection does not decide presentation.
- Watchers produce structured events.
- Alert policy decides interruption.
- Hardware controllers are lazy and testable.
- Model-specific commands are disabled by default.
- Experimental commands live behind Project Stargate interlocks.
- Recovery behavior is as important as activation behavior.
- The LCD width is always treated as a hard 16-character boundary.

## Testing

The suite covers unit, contract, integration, and hardware-abstraction behavior. Physical hardware tests remain separate and must be explicitly supervised.

At the July 19, 2026 consolidation, the full suite passed 861 tests.

When changing display behavior, update the current Flight Deck contract rather than preserving retired visual layouts. Git history already preserves earlier generations.

## Hardware changes

Before adding a write:

1. identify the exact controller;
2. document the address or register;
3. verify the command on the intended model;
4. verify restoration;
5. isolate it behind a controller class;
6. add duplicate suppression where useful;
7. add tests with a recording transport;
8. default the feature off for portable configurations;
9. document the support boundary.

## Documentation

User-visible features are incomplete until the README, relevant technical manual, configuration reference, and history or roadmap are updated.

## Commit messages

Examples:

```text
feat: add verified TVS-671 bay identify LED control
fix: consume A125 ownership reply
docs: redefine TruePanel as an independent platform
chore: curate Stargate laboratory source tree
```

## Release promotion

A release candidate should have:

- a clean `develop` tree;
- a synchronized remote;
- a complete passing suite;
- current installation and hardware documentation;
- reviewed `main`-only commits;
- an explicit merge or release commit;
- a tag when appropriate.
