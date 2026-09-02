from truepanel.holodeck.aegis_passive_runtime import (
    run_passive_runtime_rehearsal,
)


def test_governed_runtime_rehearsal_is_safe_and_bounded():
    proof = run_passive_runtime_rehearsal()
    metrics = proof["measurements"]
    assert proof["hardware_isolated"] is True
    assert proof["field_validated"] is False
    assert proof["control_authority"] is False
    assert metrics["positive_runtime_status"] == "READY"
    assert metrics["delegate_calls_first_observation"] == 3
    assert metrics["delegate_calls_after_second_observation"] == 3
    assert metrics["second_observation_query_reduction_percent"] == 100.0
    assert metrics["negative_holds"] == 4
    assert metrics["unsafe_false_ready"] == 0
    assert metrics["mutating_method_calls"] == 0
    assert metrics["stale_cache_can_clear_recovery"] is False
    assert metrics["runtime_receipt_writes"] == 0
