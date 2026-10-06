"""Contracts for final-consumer roster enrollment binding."""

import inspect
import json
from pathlib import Path

from truepanel.aegis.field_ceremony import assess_field_ceremony, build_parser
from truepanel.holodeck.aegis_roster_enrollment_binding import (
    run_roster_enrollment_binding_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_final_consumer_reaudits_public_roster_enrollment():
    evidence = run_roster_enrollment_binding_checkride()

    assert evidence["status_counts"] == {
        "ACTION_REQUIRED_SIGNING_KIT_EXPORT": 1,
        "HOLD": 7,
    }
    measurements = evidence["measurements"]
    assert measurements["enrollment_bound_consumers"] == 1
    assert measurements["raw_roster_bypasses_accepted"] == 0
    assert measurements["same_principal_substitutions_accepted"] == 0
    assert measurements["unsafe_ready"] == 0
    assert measurements["production_acceptances"] == 0
    assert measurements["deployments"] == 0
    assert measurements["hardware_actions"] == 0
    assert measurements["runtime_writes"] == 0
    assert evidence["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}

    parameters = inspect.signature(assess_field_ceremony).parameters
    assert "roster_enrollment_receipt_path" in parameters
    assert "operator_confirmed_fingerprint" in parameters
    options = {option for action in build_parser()._actions for option in action.option_strings}
    assert "--roster-enrollment-receipt" in options
    assert "--operator-confirmed-fingerprint" in options


def test_preserved_roster_enrollment_binding_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-roster-enrollment-binding-v1.json").read_text()
    )
    assert preserved == run_roster_enrollment_binding_checkride()


def test_mission_control_names_roster_enrollment_binding():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Final consumer · re-audits roster enrollment + fingerprint" in source
    assert "Raw roster-only path · HOLD" in source
