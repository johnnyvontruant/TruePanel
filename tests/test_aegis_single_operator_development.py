import inspect
import json
from copy import deepcopy
from pathlib import Path

from truepanel.aegis import (
    DEVELOPMENT_RESULT_SCHEMA,
    authority_boundary,
    evaluate_manual_promotion,
)
from truepanel.hardware import commands as hardware_commands
from truepanel.holodeck.aegis_single_operator_development import (
    run_single_operator_development_checkride,
)
from truepanel.upgrade import promotion as upgrade_promotion

ROOT = Path(__file__).resolve().parents[1]


def test_checkride_allows_one_development_review_and_denies_stronger_consumers():
    report = run_single_operator_development_checkride()
    assert report["status_counts"] == {
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 9,
        "DENIED": 5,
    }
    assert report["measurements"] == {
        "development_eligible": 1,
        "stronger_consumers_denied": 5,
        "false_eligible_paths": 0,
        "production_acceptances": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "storage_writes": 0,
        "network_changes": 0,
        "automatic_promotions": 0,
        "runtime_writes": 0,
    }
    assert report["production_mutation"] is False
    assert report["control_authority"] is False


def test_development_result_cannot_be_relabelled_for_production():
    artifact = {
        "schema": DEVELOPMENT_RESULT_SCHEMA,
        "status": "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW",
    }
    assert (
        authority_boundary(artifact, "development_candidate_review")["status"]
        == "ALLOWED"
    )
    for capability in (
        "production_acceptance",
        "deployment",
        "hardware_actuation",
        "storage_write",
        "network_reconfiguration",
    ):
        assert authority_boundary(artifact, capability)["status"] == "DENIED"

    forged = deepcopy(artifact)
    forged["status"] = "ELIGIBLE_FOR_OPERATOR_PROMOTION"
    result = evaluate_manual_promotion(
        request={},
        candidate={},
        stage_manifest={},
        observed_stage_tree_sha256="",
        acceptance=forged,
        receipt={},
        preflight={},
    )
    assert result["status"] == "HOLD"
    assert result["reason"] == "RequestSchemaInvalid"
    independent = next(
        item
        for item in result["conditions"]
        if item["condition"] == "independent_review"
    )
    assert independent["passed"] is False


def test_deploy_and_hardware_entrypoints_accept_no_aegis_receipt():
    for function in (
        upgrade_promotion.run_promotion,
        hardware_commands.handle_hardware_command,
    ):
        parameters = inspect.signature(function).parameters
        assert not (
            {"aegis_receipt", "review_receipt", "development_receipt"} & set(parameters)
        )


def test_preserved_single_operator_evidence_replays_exactly():
    archived = json.loads(
        (ROOT / "docs/evidence/aegis-single-operator-development-v1.json").read_text()
    )
    assert run_single_operator_development_checkride() == archived


def test_mission_control_labels_real_authority_boundary_on_mobile():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Single operator · development only" in source
    assert "Production authority · NO" in source
    assert "Deployment · NO" in source
    assert "Hardware · NO" in source
    assert ".ag-dev-review" in source
