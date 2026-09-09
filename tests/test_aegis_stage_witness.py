import json
from pathlib import Path

import truepanel.aegis.stage_witness as stage_witness_module
from truepanel.aegis.promotion_gate import build_witnessed_promotion_request
from truepanel.aegis.stage_witness import witness_validated_stage
from truepanel.holodeck.aegis_stage_witness import run_stage_witness_checkride
from truepanel.upgrade.promotion import MANIFEST_NAME

ROOT = Path(__file__).resolve().parents[1]


def _stage(tmp_path: Path, *, version: str = "1.3.0") -> Path:
    stage = tmp_path / ".truepanel-stage-test"
    (stage / "truepanel").mkdir(parents=True)
    (stage / "truepanel" / "payload.py").write_text("VALUE = 1\n", encoding="utf-8")
    (stage / "truepanel.yaml").write_text("private: preserved\n", encoding="utf-8")
    (stage / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "state": "validated",
                "stage_root": str(stage),
                "deploy_root": str(tmp_path / "TruePanel"),
                "source_version": version,
                "deployed_version": "1.2.0",
                "promotion_performed": False,
                "services_modified": False,
            }
        ),
        encoding="utf-8",
    )
    return stage


def test_real_stage_is_witnessed_and_bound_without_writes(tmp_path):
    stage = _stage(tmp_path)
    result = build_witnessed_promotion_request(
        request_id="test-stage-v1",
        candidate={"truepanel_version": "1.3.0"},
        stage_root=str(stage),
        backup_root=str(tmp_path / ".truepanel-backup-test"),
        nonce="test-nonce-00000000000001",
    )

    assert result["status"] == "READY_FOR_EXTERNAL_REVIEW"
    assert result["request"]["stage_tree_sha256"] == result["witness"][
        "stage_tree_sha256"
    ]
    assert result["witness"]["entry_count"] == 1
    assert result["review_signatures"] == 0
    assert result["filesystem_writes"] == 0
    assert result["promotion_performed"] is False
    assert result["control_authority"] is False


def test_stage_digest_changes_when_promoted_payload_changes(tmp_path):
    stage = _stage(tmp_path)
    before = witness_validated_stage(stage)
    (stage / "truepanel" / "payload.py").write_text("VALUE = 2\n", encoding="utf-8")
    after = witness_validated_stage(stage)

    assert before["status"] == after["status"] == "WITNESSED"
    assert before["stage_tree_sha256"] != after["stage_tree_sha256"]


def test_preserved_configuration_is_outside_promoted_payload_digest(tmp_path):
    stage = _stage(tmp_path)
    before = witness_validated_stage(stage)
    (stage / "truepanel.yaml").write_text("private: changed\n", encoding="utf-8")
    after = witness_validated_stage(stage)

    assert before["stage_tree_sha256"] == after["stage_tree_sha256"]


def test_payload_symlink_fails_closed(tmp_path):
    stage = _stage(tmp_path)
    outside = tmp_path / "outside"
    outside.write_text("not staged\n", encoding="utf-8")
    (stage / "truepanel" / "escape").symlink_to(outside)

    result = witness_validated_stage(stage)

    assert result["status"] == "HOLD"
    assert result["reason"] == "StageSymlinkRejected"
    assert result["stage_tree_sha256"] is None


def test_post_read_change_during_witness_fails_closed(tmp_path, monkeypatch):
    stage = _stage(tmp_path)
    original = stage_witness_module._read_regular

    def mutate_after_read(path, before, *, capture=False):
        result = original(path, before, capture=capture)
        if path.name == "payload.py":
            path.write_text("VALUE = 3\n", encoding="utf-8")
        return result

    monkeypatch.setattr(stage_witness_module, "_read_regular", mutate_after_read)

    result = witness_validated_stage(stage)

    assert result["status"] == "HOLD"
    assert result["reason"] == "StageChangedDuringWitness"


def test_manifest_symlink_fails_closed(tmp_path):
    stage = _stage(tmp_path)
    manifest = stage / MANIFEST_NAME
    external = tmp_path / "manifest.json"
    external.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(external)

    result = witness_validated_stage(stage)

    assert result["status"] == "HOLD"
    assert result["reason"] == "UnsafeStageManifest"


def test_platform_without_no_follow_support_fails_closed(tmp_path, monkeypatch):
    stage = _stage(tmp_path)
    monkeypatch.delattr(stage_witness_module.os, "O_NOFOLLOW")

    result = witness_validated_stage(stage)

    assert result["status"] == "HOLD"
    assert result["reason"] == "StageNoFollowUnavailable"


def test_version_mismatch_never_creates_review_request(tmp_path):
    stage = _stage(tmp_path, version="1.3.0")

    result = build_witnessed_promotion_request(
        request_id="test-stage-v1",
        candidate={"truepanel_version": "9.9.9"},
        stage_root=str(stage),
        backup_root=str(tmp_path / ".truepanel-backup-test"),
        nonce="test-nonce-00000000000001",
    )

    assert result["status"] == "HOLD"
    assert result["reason"] == "VersionMismatch"
    assert result["request"] is None


def test_stage_witness_checkride_has_one_ready_path_and_no_authority():
    report = run_stage_witness_checkride()

    assert report["status_counts"] == {
        "READY_FOR_EXTERNAL_REVIEW": 1,
        "HOLD": 5,
    }
    assert report["measurements"] == {
        "false_ready_paths": 0,
        "production_stage_writes": 0,
        "review_signatures_created": 0,
        "promotion_executions": 0,
        "service_changes": 0,
    }
    assert report["temporary_fixture_removed"] is True
    assert report["production_mutation"] is False
    assert report["control_authority"] is False


def test_preserved_stage_witness_evidence_replays_exactly():
    archived = json.loads(
        (ROOT / "docs/evidence/aegis-actual-stage-witness-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert run_stage_witness_checkride() == archived
