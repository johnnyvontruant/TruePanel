# Contributing to TruePanel

TruePanel welcomes careful improvements to the platform, documentation, tests, plugins, and hardware knowledge base.

## Development flow

1. Create a focused branch from `develop`.
2. Keep production behavior and laboratory experiments separate.
3. Add or update tests for every behavior change.
4. Run the complete suite.
5. Update documentation when commands, configuration, architecture, or hardware support changes.
6. Open a pull request describing the purpose, risk, test evidence, and hardware evidence when applicable.

## Quality gate

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
python3 -m compileall -q truepanel
bash -n install.sh
bash -n uninstall.sh
git diff --check
```

The working tree should contain no caches, compiled probes, extracted firmware, runtime plugin state, or timestamped backup files.

## Hardware contributions

Hardware support requires stronger evidence than ordinary software changes.

A hardware pull request should identify:

- exact QNAP model
- operating system and kernel
- controller or device path
- command bytes or register behavior
- passive observations performed first
- restoration behavior
- failure behavior
- test or capture evidence
- safety boundaries

Do not submit broad I2C scans, destructive disk tests, unexplained firmware binaries, secrets, or commands that cannot be bounded to a known device.

## Project Stargate

New protocol experiments should use the existing catalog, classifier, authorization, cooldown, session, evidence, and execution-service layers. A standalone probe belongs under `development/` only when it preserves reproducible discovery work not yet represented in the guarded CLI.

## Code style

- Target Python 3.11.
- Prefer small components with explicit responsibilities.
- Keep the normal display calm and make alerts proportional to severity.
- Preserve 16-character LCD constraints.
- Avoid shell-dependent behavior when a safe Python implementation is practical.
- Keep comments focused on why a safety or design choice exists.

## Commit messages

Use concise imperative messages. Conventional prefixes such as `feat:`, `fix:`, `docs:`, `test:`, `chore:`, and `release:` are encouraged.

## License

By contributing, you agree that your contribution may be distributed under the MIT License.
