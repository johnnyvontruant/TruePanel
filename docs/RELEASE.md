# Release Process

TruePanel releases use a dedicated `release/vX.Y.Z` branch and annotated Git tags.

Release-candidate package versions use `X.Y.ZrcN` and candidate tags use
`vX.Y.Z-rcN`. The final stable release uses version `X.Y.Z` and tag
`vX.Y.Z`.

## Release preparation

- Start from synchronized and validated `main`.
- Create `release/vX.Y.Z` from the graduated commit.
- For a release candidate, set `truepanel.__version__` to `X.Y.ZrcN`.
- Update package metadata and `CHANGELOG.md`.
- Run the release contract and complete test suite.
- Confirm documentation links, installer syntax, and a clean repository.
- Push the release branch for review.

## Installed-system validation

Synchronize the release candidate into the reference TrueNAS system using `install.sh`.

Verify:

```bash
/mnt/POOL/DATASET/TruePanel/bin/truepanel version
/mnt/POOL/DATASET/TruePanel/bin/truepanel doctor
systemctl restart truepanel
systemctl is-active truepanel
journalctl -u truepanel -n 100 --no-pager
```

Observe at least one complete Flight Deck rotation. Confirm button navigation, centered identity and IP pages, storage pages, and normal bay LED state.

## Release-candidate acceptance gate

A release candidate must satisfy all of the following:

- candidate version metadata uses `X.Y.ZrcN`;
- candidate Git tag uses `vX.Y.Z-rcN`;
- version metadata is sourced from `truepanel.__version__`;
- installer and uninstaller syntax are valid;
- complete automated test suite passes;
- installed-system validation passes;
- release evidence is preserved.

## Stable release acceptance gate

Before final stable publication, remove the RC suffix. The stable product
version must have no prerelease suffix.

The stable release must satisfy all of the following:

- no prerelease suffix in the product version
- version metadata sourced from `truepanel.__version__`
- release policy files present
- installer and uninstaller syntax valid
- complete automated test suite passing
- no tracked caches, backups, firmware extractions, runtime state, or credentials
- `main` and the release commit reconciled
- installed CLI reports the release version
- service restarts and remains active
- rollback path documented

## Promote a release candidate to stable

Promote only from a release candidate that has already passed the installed-system
acceptance gate. Keep the promotion diff limited to release metadata,
documentation, and release-contract assertions unless a genuine blocker is found.

1. Create a short-lived promotion branch from `release/vX.Y.Z`.
2. Change `truepanel.__version__` and `[project].version` from `X.Y.ZrcN` to
   `X.Y.Z`.
3. Add the final `X.Y.Z` section to `CHANGELOG.md` while preserving the RC
   history below it.
4. Update release-contract assertions so the stable version cannot regress to
   a prerelease identifier or drift from package metadata.
5. Run the release-contract tests and complete canonical test suite.
6. Build and smoke-test the installed wheel in a clean environment.
7. Merge the promotion branch into `release/vX.Y.Z` only after CI passes.
8. Run CI against the exact resulting release-branch commit and preserve the
   evidence.
9. Reconcile `main` with the tested release tree without introducing additional
   product changes. If reconciliation creates a new commit, rerun CI on that
   exact commit before tagging it.
10. Create `vX.Y.Z` only on a commit whose exact contents passed the stable
    acceptance gate. Never move an existing release tag.

## Publish a release candidate

After candidate acceptance:

1. Push `release/vX.Y.Z`.
2. Run CI against the exact candidate commit.
3. Create annotated tag `vX.Y.Z-rcN`.
4. Push the candidate tag.
5. Publish candidate release notes from `CHANGELOG.md`.
6. Preserve candidate validation evidence.
7. Keep the release branch open for subsequent RC fixes.

## Publish the stable release

After stable acceptance:

1. Merge `release/vX.Y.Z` into `main`.
2. Create annotated tag `vX.Y.Z` on the tested stable commit.
3. Push `main` and the stable tag.
4. Publish GitHub release notes from `CHANGELOG.md`.
5. Preserve the release audit and installation evidence.

## Hotfixes

Create `hotfix/vX.Y.Z` from the affected stable tag. Keep the change narrow, add a regression test, repeat the installed-system validation, and merge the fix into `main`.
