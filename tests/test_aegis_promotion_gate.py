from truepanel.holodeck.aegis_promotion_gate import run_manual_promotion_checkride


def test_manual_promotion_gate_has_one_ready_path_and_no_execution():
    report = run_manual_promotion_checkride()
    assert report["status_counts"] == {"READY_FOR_MANUAL_PROMOTION": 1, "HOLD": 8}
    assert report["measurements"] == {
        "false_ready_paths": 0,
        "promotion_executions": 0,
        "receipt_consumptions": 0,
        "service_changes": 0,
        "runtime_writes": 0,
    }
    assert report["production_mutation"] is False
    assert report["control_authority"] is False


def test_every_unsafe_promotion_path_holds():
    report = run_manual_promotion_checkride()
    statuses = {item["scenario"]: item["status"] for item in report["scenarios"]}
    assert statuses.pop("reviewed-pristine-stage") == "READY_FOR_MANUAL_PROMOTION"
    assert set(statuses.values()) == {"HOLD"}
