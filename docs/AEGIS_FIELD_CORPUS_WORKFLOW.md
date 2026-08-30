# AEGIS field corpus workflow

Status: operator-ready, read-only evidence workflow; not production validation.

This workflow closes the gap between an opt-in Black Box recording and a
reviewable AEGIS evidence assessment. It never captures live telemetry by
itself, retains no operator identity, has no control authority, and cannot
promote evidence to production validated.

## Trust boundary

The workflow advances through five explicit states:

1. **Consent** — initialize an empty workspace with the exact confirmation
   phrase, a narrow `sanitized-aegis-calibration` use, and a retention policy.
2. **Intake** — import an existing Black Box JSONL recording. Intake rejects a
   file if its stored records differ from Black Box's sanitized representation.
3. **Review** — label the expected incident outcome, system profile, and
   workload class, then confirm human review without storing reviewer identity.
4. **Freeze** — require every case to be reviewed; hash each recording and the
   canonical manifest; reject all later intake or relabeling.
5. **Assess** — replay the frozen corpus through ORACLE and AEGIS in HoloDeck,
   evaluate conservative Wilson bounds, and write a content-addressed receipt.

An automated PASS means only `field_candidate`. A separate release review is
always required, and `production_validated` remains false in every receipt.

## Operator CLI

All paths are operator-selected. The CLI has no default live collection path.

```console
truepanel holodeck field-init ./field-corpus \
  --corpus-id field-corpus-v1 \
  --retention-policy "delete on withdrawal; review annually" \
  --confirm "I CONSENT TO SANITIZED AEGIS CALIBRATION"

truepanel holodeck field-ingest ./field-corpus recording.jsonl \
  --case-id reviewed-incident-001 \
  --challenge reviewed-cooling-incident \
  --system-profile qnap-six-bay \
  --workload-class storage-workload \
  --shared-cooling

truepanel holodeck field-review ./field-corpus reviewed-incident-001 \
  --confirm "I REVIEWED THIS INCIDENT OUTCOME"

truepanel holodeck field-freeze ./field-corpus \
  --confirm "FREEZE THIS FIELD CORPUS"

truepanel holodeck field-assess ./field-corpus
truepanel holodeck field-status ./field-corpus
```

For a complete installed-package smoke test using only packaged deterministic
fixtures:

```console
truepanel holodeck field-smoke ./smoke-workflow
```

The expected smoke verdict is `lab_calibrated`, with field eligibility false,
production validation false, hardware isolation true, and control authority
false. This is intentionally a negative promotion test: synthetic fixtures
prove the plumbing, not field accuracy.

## Stored artifacts

- `workflow.json`: consent scope, state, labels, review progress, and immutable
  receipt references; no operator identity or raw source path.
- `recordings/*.jsonl`: copied sanitized-at-rest recordings with bounded total
  bytes and unique safe case identifiers.
- `manifest.json`: loader-compatible field corpus manifest with per-recording
  hashes and a canonical corpus hash.
- `assessment.json`: HoloDeck report binding, uncertainty measurements, HOLD
  reasons, and a canonical receipt hash.

Atomic replace is used for metadata writes. Digest or byte tampering blocks
assessment. Source recordings are read-only inputs and are never altered.

## Known limits

- TruePanel does not establish legal consent on behalf of an organization; the
  operator must have collection authority.
- Withdrawal after freeze is handled by deleting the separately governed corpus
  and invalidating its receipt, not by rewriting history.
- The deterministic smoke corpus has only one positive recording and one system
  profile, so it correctly remains below field evidence floors.
- No live BattleStation evidence was collected by this increment.
