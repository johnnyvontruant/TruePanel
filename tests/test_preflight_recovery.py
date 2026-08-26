from truepanel.compatibility.models import CompatibilityCheck, CompatibilityReport
from truepanel.web.preflight import PREFLIGHT_SCHEMA_VERSION, build_preflight_payload


def _report(*checks, classification="REVIEW"):
    return CompatibilityReport(
        classification=classification,
        installation_mode="native",
        hardware_control="locked",
        checks=tuple(checks),
    )


def _section(payload, section_id):
    return next(section for section in payload["sections"] if section["id"] == section_id)


def test_review_explains_path_to_machine_verified_pass():
    payload = build_preflight_payload(
        _report(
            CompatibilityCheck(
                status="REVIEW",
                name="Host Identity",
                detail="OEM DMI identity is incomplete.",
            ),
            CompatibilityCheck(
                status="REVIEW",
                name="Storage Topology",
                detail="One bay mapping needs verification.",
            ),
        )
    )

    assert PREFLIGHT_SCHEMA_VERSION == 1
    assert payload["flight_status"] == "REVIEW"
    assert payload["recovery"]["verification"] == "rerun_passive_compatibility_survey"
    assert payload["recovery"]["manual_pass_allowed"] is False

    host = _section(payload, "host")
    storage = _section(payload, "storage")
    assert host["review"]["pending_checks"] == 1
    assert storage["review"]["pending_checks"] == 1
    assert host["checks"][0]["review"]["reason"] == "OEM DMI identity is incomplete."
    assert host["checks"][0]["review"]["machine_pass_required"] is True
    assert host["checks"][0]["review"]["manual_pass_allowed"] is False


def test_passed_preflight_resolves_without_operator_override():
    payload = build_preflight_payload(
        _report(
            CompatibilityCheck(
                status="PASS",
                name="Host Identity",
                detail="Host identity verified.",
            ),
            CompatibilityCheck(
                status="PASS",
                name="Storage Topology",
                detail="Storage topology verified.",
            ),
            classification="SUPPORTED",
        )
    )

    assert payload["flight_status"] == "READY"
    assert payload["recovery"]["state"] == "resolved"
    assert _section(payload, "host")["review"]["review_required"] is False
    assert _section(payload, "storage")["review"]["review_required"] is False


def test_failed_check_stays_blocked_until_evidence_changes():
    payload = build_preflight_payload(
        _report(
            CompatibilityCheck(
                status="FAIL",
                name="Storage Safety",
                detail="Required passive storage evidence failed.",
            ),
            classification="UNSUPPORTED",
        )
    )

    check = _section(payload, "storage")["checks"][0]
    assert payload["flight_status"] == "HOLD"
    assert check["review"]["state"] == "blocked"
    assert check["review"]["rerun_available"] is True
    assert check["review"]["manual_pass_allowed"] is False
