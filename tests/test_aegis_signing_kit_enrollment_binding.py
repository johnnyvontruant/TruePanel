"""Contracts for final-consumer signing-kit enrollment binding."""

import inspect
import json
from pathlib import Path

from truepanel.aegis.field_ceremony import assess_field_ceremony
from truepanel.holodeck.aegis_signing_kit_enrollment_binding import (
    run_signing_kit_enrollment_binding_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_final_consumer_binds_kit_to_enrolled_key_identity():
    evidence = run_signing_kit_enrollment_binding_checkride()

    assert evidence["status_counts"] == {
        "ACTION_REQUIRED_INDEPENDENT_KIT_AUDIT": 1,
        "ACTION_REQUIRED_SIGNING_KIT_EXPORT": 1,
        "HOLD": 5,
    }
    assert evidence["measurements"]["enrollment_bound_kits"] == 1
    assert evidence["measurements"]["same_principal_foreign_kits_accepted"] == 0
    assert evidence["measurements"]["identity_substitutions_accepted"] == 0
    assert evidence["measurements"]["unsafe_ready"] == 0
    source = inspect.getsource(assess_field_ceremony)
    assert 'internal.get("public_key_fingerprint")' in source
    assert 'internal.get("operator_key_id")' in source


def test_preserved_signing_kit_enrollment_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-signing-kit-enrollment-binding-v1.json").read_text()
    )
    assert preserved == run_signing_kit_enrollment_binding_checkride()


def test_mission_control_names_signing_kit_enrollment_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Signing kit · bound to enrolled fingerprint" in source
    assert "Same-principal foreign-key kit · HOLD" in source
    assert "unsigned enrollment receipt is not operator authentication" in source
