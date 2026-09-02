from truepanel.holodeck.aegis_passive_providers import (
    run_passive_provider_rehearsal,
)


def test_passive_provider_rehearsal_fails_closed():
    result = run_passive_provider_rehearsal()
    measurements = result["measurements"]
    assert result["hardware_isolated"] is True
    assert result["field_validated"] is False
    assert result["control_authority"] is False
    assert result["positive_ledger"]["status"] == "EVIDENCE_READY"
    assert measurements == {
        "documented_query_methods": 3,
        "mutating_methods": 0,
        "positive_statements_accepted": 2,
        "negative_holds": 3,
        "unsafe_false_ready": 0,
        "task_success_promoted_without_restore_test": False,
    }
