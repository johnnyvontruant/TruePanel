# CHECKRIDE Pre-Service Clearance

This increment closes the seam between a diagnosed storage incident and an
operator-reviewed external service plan. It adds no repair endpoint and grants
no hardware or storage-write authority.

## Contract

CHECKRIDE emits exactly one incident-bound clearance receipt. Its state is
either `HOLD` or `READY_FOR_OPERATOR_REVIEW`. The latter means only that a
human may review the external service procedure; it never means that TruePanel
may offline, remove, replace, wipe, or reconfigure a disk.

The receipt fails closed unless all seven gates pass:

1. The live incident and complete bay/device/model/serial/pool/VDEV identity
   are bound to the current snapshot.
2. Current topology retains at least one additional member of fault tolerance.
3. An independent backup source has a tested restore and a fresh attestation.
4. A model-specific service procedure retains source provenance.
5. One fresh replacement is distinct, equal-or-larger, outside every pool,
   and free of preserved-data risk.
6. No resilver is active.
7. Provider statements are fresh, incident-bound, digest-intact, strongly
   identified, governed, and free of ambiguity or contradiction.

Evidence expires after 15 minutes. The canonical receipt has a SHA-256 digest,
so later screenshots or reports can be reconciled to the exact gate inputs.
The embedded evidence ledger separately discloses that its SHA-256 proves
mutation resistance, not provider authenticity.
Mission Control keeps failed gates visible and preserves single-column phone
reflow. It uses the existing shared status event and adds no polling.

## Prior art and provenance

The design adapts semantics, not source code:

- [TrueNAS disk replacement guidance](https://www.truenas.com/docs/scale/25.04/scaletutorials/storage/disks/replacingdisks/)
  treats serial-number confirmation as crucial and requires an equal-or-larger
  replacement. CHECKRIDE makes both machine-visible gates.
- [OpenZFS `zpool-replace`](https://openzfs.github.io/openzfs-docs/man/master/8/zpool-replace.8.html)
  documents the minimum-size rule and the legitimate same-device-path case.
  CHECKRIDE therefore requires distinct hardware identity instead of treating
  `/dev/sdX` as durable identity.
- [NIST SP 1339](https://www.nist.gov/publications/ot-backup-quick-start-guide)
  emphasizes regular, tested backups and review during recovery exercises.
  A checkbox acknowledgement alone is intentionally insufficient here.

No external code, data, binary, model, dependency, credential, or
notice-bearing artifact was incorporated. TruePanel owns the interface and can
replace its policy without changing Mission Control consumers.

## Reproduction

```console
pytest -q tests/test_checkride.py
node --check truepanel/web/static/reliability-view.js
python -m truepanel.hangar validate --root .
```

The preserved deterministic artifact is
`docs/evidence/checkride-pre-service-clearance-v1.json`. That original fixture
passed 6/6 gates. The ground-truth follow-up adds a seventh provider-integrity
gate while both physical-service and storage-write authority remain false.
Negative paths now also cover mutated statements, ungoverned providers, reused
identities, and ambiguous duplicates.

## Rejected paths

- Treating an operator backup acknowledgement as restore evidence: rejected.
- Trusting a candidate only because it has sufficient nominal capacity:
  rejected; identity, pool membership, data risk, and freshness are separate.
- Persisting a long-lived READY state: rejected; every receipt expires.
- Reusing Linux device names as physical identity: rejected.
- Turning READY into an execution capability: rejected; authority stays false.

## Remaining field gate

The live incident should remain on HOLD until a real replacement candidate,
tested backup evidence, and fresh service-time identity arrive through governed
read-only sources. The ongoing CHECKRIDE experiment remains `IN_PROGRESS`
until an external repair produces a passing or evidence-backed failing repair
signature.
