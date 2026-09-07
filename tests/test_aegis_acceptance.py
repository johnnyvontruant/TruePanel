from truepanel.holodeck.aegis_acceptance import run_acceptance_checkride


def test_independent_review_checkride_fails_closed():
    report = run_acceptance_checkride()
    assert report["old_envelope_after_upgrade"]["status"] == "HOLD"
    assert report["status_counts"] == {"ELIGIBLE_FOR_OPERATOR_PROMOTION": 1, "HOLD": 7}
    assert report["measurements"] == {
        "false_eligible_paths": 0,
        "private_keys_persisted": 0,
        "candidate_installations": 0,
        "automatic_acceptances": 0,
        "runtime_writes": 0,
    }
    assert report["production_signer_present"] is False
    assert report["production_mutation"] is False
    assert report["control_authority"] is False


def test_every_unsafe_route_holds():
    report = run_acceptance_checkride()
    statuses = {x["scenario"]: x["status"] for x in report["scenarios"]}
    assert statuses["two-reviewer-quorum"] == "ELIGIBLE_FOR_OPERATOR_PROMOTION"
    assert all(
        status == "HOLD"
        for name, status in statuses.items()
        if name != "two-reviewer-quorum"
    )
