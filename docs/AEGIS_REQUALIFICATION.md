# AEGIS Airworthiness Requalification

Project REQUALIFICATION gives AIRWORTHINESS an evidence-backed path out of
HOLD without letting AEGIS approve itself. It is HANGAR experiment
`TP-EXP-0022`.

## Contract

A successor proposal must:

- name the canonical SHA-256 of the exact accepted predecessor;
- use a new envelope identity;
- start no earlier than its predecessor, not postdate the appraisal clock, and
  expire within 92 days;
- preserve or increase a safely orderable stable TrueNAS release;
- match the current runtime subjects, correlation policy, Recovery Coverage
  Matrix, and governed platform witness;
- bind the exact requalification evaluator; and
- require operator review while declaring automatic acceptance false.

Passing produces only `READY_FOR_OPERATOR_REVIEW`. The evaluator has no file
write, installation, deployment, service, credential, or control path. The
accepted envelope remains unchanged until an external review process replaces
it.

Mission Control now attaches an always-visible `NEXT` instruction to the
AIRWORTHINESS strip. CURRENT says to preserve evidence and monitor expiry;
REVIEW requests fresh governed evidence; platform drift requests a successor
rehearsal and independent review; other HOLD states request targeted
revalidation. Detailed evidence remains in the existing disclosure, and the
shared status stream remains the only browser update path.

## Deterministic upgrade proof

HoloDeck first presents TrueNAS 25.10.6 to the accepted 25.10.5 envelope. The
old envelope correctly returns `HOLD / PlatformDrift`. Ten successor paths then
produce:

- 2 `READY_FOR_OPERATOR_REVIEW`: coherent upgrade and same-platform renewal;
- 2 `REVIEW`: missing platform witness and vendor prerelease ordering that the
  stable comparator cannot safely infer;
- 6 `HOLD`: wrong predecessor, downgrade, excessive validity, automatic
  acceptance, renewal-contract drift, and runtime-subject drift.

There are zero false-ready paths, candidate installations, automatic
acceptances, runtime writes, production mutations, or control authority. The
preserved artifact is
[`evidence/aegis-airworthiness-requalification-v1.json`](evidence/aegis-airworthiness-requalification-v1.json).

Reproduce with:

```console
pytest -q tests/test_aegis_requalification.py tests/test_aegis_assurance.py tests/test_aegis.py
python -c "from truepanel.holodeck.aegis_requalification import run_requalification_rehearsal as run; print(run())"
python -m truepanel.hangar validate --root .
node --check truepanel/web/static/reliability-view.js
```

## Prior art and provenance

- [The Update Framework](https://theupdateframework.github.io/specification/latest/)
  supplies adaptable lineage, expiry, rollback, and mix-and-match defenses.
- [SLSA artifact verification](https://slsa.dev/spec/v1.2/verifying-artifacts)
  distinguishes summarized verification evidence from consumer acceptance
  policy.
- [IETF RATS](https://www.rfc-editor.org/rfc/rfc9334.html) separates evidence
  collection, appraisal, and relying-party decisions.
- [NIST SP 800-128](https://csrc.nist.gov/pubs/sp/800/128/upd1/final)
  supports documented, impact-analyzed configuration changes and separate test
  environments.

No external code, schema, library, service, key, or notice-bearing artifact was
incorporated. Full TUF signing and hosted transparency were deferred until
TruePanel has a governed reviewer identity and signing-key lifecycle.

## Failed paths and next step

Automatic installation after passing simulation was rejected because it
collapses evidence, appraisal, and authority. Vendor prerelease ordering was
not guessed. A same-ID proposal, unbounded validity window, downgrade, missing
lineage, and changed subjects all fail closed.

The strongest next step is an operator-signed acceptance receipt with explicit
reviewer role, threshold policy, expiry, and revocation rehearsal, followed by
an isolated pre-upgrade checkride. No production update should depend on that
work until the key lifecycle is governed.
