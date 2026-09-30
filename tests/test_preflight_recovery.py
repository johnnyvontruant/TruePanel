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



def test_known_ambiguous_qnap_identity_offers_operator_verification():
    payload = build_preflight_payload(
        _report(
            CompatibilityCheck(
                status="REVIEW",
                name="QNAP Identity",
                detail=(
                    "INSYDE / QW56; OEM DMI may not expose "
                    "the chassis manufacturer"
                ),
            ),
        ),
        identity_review={
            "detected_identity": "INSYDE / QW56",
            "confirmable": True,
            "candidate_model": "TVS-671",
            "verified": False,
            "binding": "current_hardware_fingerprint",
        },
    )

    check = _section(payload, "host")["checks"][0]
    review = check["review"]

    assert review["operator_verification_allowed"] is True
    assert review["candidate_model"] == "TVS-671"
    assert review["manual_pass_allowed"] is False
    assert (
        review["verification_binding"]
        == "current_hardware_fingerprint"
    )


def test_operator_verified_qnap_identity_reports_provenance():
    payload = build_preflight_payload(
        _report(
            CompatibilityCheck(
                status="PASS",
                name="QNAP Identity",
                detail=(
                    "INSYDE / QW56; operator verified QNAP TVS-671"
                ),
            ),
            classification="SUPPORTED",
        ),
        identity_review={
            "detected_identity": "INSYDE / QW56",
            "confirmable": False,
            "verified": True,
            "verified_model": "TVS-671",
            "binding": "current_hardware_fingerprint",
        },
    )

    check = _section(payload, "host")["checks"][0]
    assert check["review"]["verification_source"] == "operator"
    assert check["review"]["verified_model"] == "TVS-671"
