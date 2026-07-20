# Release Process

TruePanel releases use a dedicated `release/vX.Y.Z` branch and an annotated Git tag.

## Release preparation

- Start from synchronized `main` and `develop`.
- Create the release branch.
- Set the stable version in `truepanel.__version__`.
- Update package metadata and `CHANGELOG.md`.
- Run the release contract and complete test suite.
- Confirm documentation links, installer syntax, and a clean repository.
- Push the release branch for review.

## Installed-system validation

Synchronize the release candidate into the reference TrueNAS system using `install.sh`.

Verify:

```bash
/opt/truepanel/bin/truepanel version
/opt/truepanel/bin/truepanel doctor
systemctl restart truepanel
systemctl is-active truepanel
journalctl -u truepanel -n 100 --no-pager
```

Observe at least one complete Flight Deck rotation. Confirm button navigation, centered identity and IP pages, storage pages, and normal bay LED state.

## Release acceptance gate

The release must satisfy all of the following:

- no prerelease suffix in the product version
- version metadata sourced from `truepanel.__version__`
- release policy files present
- installer and uninstaller syntax valid
- complete automated test suite passing
- no tracked caches, backups, firmware extractions, runtime state, or credentials
- `main`, `develop`, and the release commit reconciled
- installed CLI reports the release version
- service restarts and remains active
- rollback path documented

## Publish

After acceptance:

1. Merge the release branch into `main`.
2. Fast-forward or merge `main` into `develop`.
3. Create an annotated `vX.Y.Z` tag on the tested release commit.
4. Push both branches and the tag.
5. Publish GitHub release notes from `CHANGELOG.md`.
6. Preserve the release audit and installation evidence.

## Hotfixes

Create `hotfix/vX.Y.Z` from the affected stable tag. Keep the change narrow, add a regression test, repeat the installed-system validation, and merge the fix into both `main` and `develop`.
