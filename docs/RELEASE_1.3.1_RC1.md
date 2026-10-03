# TruePanel 1.3.1-rc1 Release Notes

TruePanel 1.3.1-rc1 is a maintenance candidate for the 1.3 reliability and
guided-recovery line.

## Highlights

- Restores complete drive-temperature telemetry.
- Restores complete SMART telemetry.
- Surfaces unresolved ZFS members without guessing their physical bay.
- Fixes storage-bay LED latching and thermal LED reconciliation.
- Adds operator chassis verification to Preflight.
- Adds a read-only VPN status annunciator.

## Safety boundaries

- Physical bay identity remains fail-closed.
- Logical storage evidence cannot create a physical bay assignment.
- Bay Mirror remains privacy-safe.
- No new destructive storage or hardware-control authority is introduced.

## RC1 acceptance gate

Before tagging `v1.3.1-rc1`:

1. GitHub Actions must pass on the exact release-branch commit.
2. Installed-wheel smoke must pass.
3. Both canonical version sources must report `1.3.1rc1`.
4. RC1 must pass guarded BattleStation deployment.
5. Both TruePanel services must remain active.
6. Drive-temperature and SMART population must remain complete.
7. Bay Mirror must surface unresolved storage state without inferring a bay.
8. Applicable Host, Preflight, and verification checks must pass.
9. Release evidence must be preserved before tagging.

## AEGIS assurance evidence

Existing 1.3.0 AEGIS assurance envelopes remain unchanged. They are historical
evidence bound to their recorded version, subject hashes, platform witness, and
review lineage. A successor envelope requires governed requalification and
operator review.
