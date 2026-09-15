#!/usr/bin/env python3
"""Smoke the installed AEGIS AIRWORTHINESS chain outside the source checkout."""

from __future__ import annotations

from truepanel.aegis.assurance import load_assurance_envelope
from truepanel.holodeck.aegis_assurance import run_airworthiness_rehearsal
from truepanel.holodeck.aegis_final_handoff import run_final_handoff_checkride
from truepanel.holodeck.aegis_requalification import run_requalification_rehearsal


def main() -> int:
    envelope = load_assurance_envelope()
    assert envelope["schema_version"] == 1
    assert envelope["envelope_id"] == "aegis-airworthiness-battlestation-v2"
    assert envelope["platform_product"] == "TrueNAS SCALE"
    assert envelope["platform_witness_required"] is True
    assert len(envelope["subjects"]) == 9

    airworthiness = run_airworthiness_rehearsal()
    assert airworthiness["hardware_isolated"] is True
    assert airworthiness["production_mutation"] is False
    assert airworthiness["control_authority"] is False
    assert airworthiness["status_counts"] == {
        "CURRENT": 1,
        "REVIEW": 1,
        "HOLD": 6,
    }

    requalification = run_requalification_rehearsal()
    assert requalification["hardware_isolated"] is True
    assert requalification["production_mutation"] is False
    assert requalification["control_authority"] is False
    assert requalification["measurements"]["false_review_ready_paths"] == 0
    assert requalification["measurements"]["candidate_installations"] == 0
    assert requalification["measurements"]["automatic_acceptances"] == 0
    assert requalification["measurements"]["runtime_writes"] == 0

    handoff = run_final_handoff_checkride()
    assert handoff["status_counts"] == {
        "READY_FOR_OPERATOR_CONFIRMATION": 1,
        "HOLD": 9,
    }
    assert all(value == 0 for value in handoff["measurements"].values())

    print(
        "PASS: installed AEGIS AIRWORTHINESS envelope, requalification, "
        "and final-handoff chain"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
