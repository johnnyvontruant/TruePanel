"""Contracts for final-consumer verifier handoff binding."""

import inspect
import json
from pathlib import Path

from truepanel.aegis.field_ceremony import assess_field_ceremony, build_parser
from truepanel.holodeck.aegis_field_handoff_binding import (
    run_field_handoff_binding_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_final_consumer_reaudits_handoff_and_rejects_raw_receipt_path():
    evidence = run_field_handoff_binding_checkride()

    assert evidence["status_counts"] == {
        "ACTION_REQUIRED_PUBLIC_ROSTER": 1,
        "DENIED": 1,
        "HOLD": 7,
    }
    measurements = evidence["measurements"]
    assert measurements["release_bound_consumers"] == 1
    assert measurements["raw_receipt_bypasses_denied"] == 1
    assert measurements["unsafe_ready"] == 0
    assert measurements["production_acceptances"] == 0
    assert measurements["deployments"] == 0
    assert measurements["hardware_actions"] == 0
    assert measurements["runtime_writes"] == 0
    assert evidence["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}

    parameters = inspect.signature(assess_field_ceremony).parameters
    assert "verifier_confirmation_receipt" not in parameters
    options = {option for action in build_parser()._actions for option in action.option_strings}
    assert "--verifier-confirmation-receipt" not in options
    assert "--verifier-confirmation-handoff" in options
    assert "--verifier-comparison-kit" in options


def test_preserved_field_handoff_binding_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-field-handoff-binding-v1.json").read_text()
    )
    assert preserved == run_field_handoff_binding_checkride()


def test_mission_control_names_final_consumer_binding():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Final consumer · re-audits handoff + comparison kit" in source
    assert "Raw receipt-only path · DENIED" in source
