import json
from pathlib import Path

from truepanel.upgrade.backup_receipt import (
    write_backup_receipt,
)
from truepanel.upgrade.cleanup import (
    CLEANUP_CONFIRMATION,
    build_cleanup_plan,
    run_cleanup,
)
from truepanel.upgrade.promotion import (
    MANIFEST_NAME,
)


def create_deployment(
    root: Path,
) -> None:
    root.mkdir(
        parents=True
    )
    (
        root / "truepanel.py"
    ).write_text("")


def create_completed_upgrade(
    parent: Path,
    deployed: Path,
    *,
    token: str,
) -> tuple[Path, Path]:
    stage = (
        parent
        / f".truepanel-stage-{token}"
    )
    backup = (
        parent
        / f".truepanel-backup-{token}"
    )

    stage.mkdir()
    backup.mkdir()

    (
        backup / "old.txt"
    ).write_text(token)

    write_backup_receipt(
        backup_root=backup,
        deploy_root=deployed,
        source_root=deployed,
        kind="promotion",
    )

    (
        stage / MANIFEST_NAME
    ).write_text(
        json.dumps(
            {
                "state": "promoted",
                "stage_root": str(
                    stage.resolve()
                ),
                "deploy_root": str(
                    deployed.resolve()
                ),
                "backup_root": str(
                    backup.resolve()
                ),
                "promotion_performed": True,
                "rollback_performed": False,
                "verification_result": 0,
            }
        )
        + "\n"
    )

    return stage, backup


def test_cleanup_keeps_newest_backup(
    tmp_path,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    create_deployment(deployed)

    old_stage, old_backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260101T000000Z",
        )
    )

    new_stage, new_backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260102T000000Z",
        )
    )

    old_backup.touch()
    old_stage.touch()
    new_backup.touch()
    new_stage.touch()

    plan = build_cleanup_plan(
        deploy_root=deployed,
    )

    actions = {
        asset.path: asset.action
        for asset in plan.assets
    }

    assert actions[old_stage] == "remove"
    assert actions[new_stage] == "remove"
    assert actions[old_backup] == "remove"
    assert actions[new_backup] == "keep"


def test_cleanup_dry_run_changes_nothing(
    tmp_path,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    create_deployment(deployed)

    stage, backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260101T000000Z",
        )
    )

    result = run_cleanup(
        deploy_root=deployed,
    )

    assert result == 0
    assert stage.exists()
    assert backup.exists()


def test_cleanup_removes_stage_but_keeps_backup(
    tmp_path,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    create_deployment(deployed)

    stage, backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260101T000000Z",
        )
    )

    result = run_cleanup(
        deploy_root=deployed,
        confirmation=(
            CLEANUP_CONFIRMATION
        ),
    )

    assert result == 0
    assert not stage.exists()
    assert backup.exists()
    assert deployed.exists()


def test_cleanup_refuses_unreferenced_backup(
    tmp_path,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    create_deployment(deployed)

    backup = (
        tmp_path
        / ".truepanel-backup-orphan"
    )
    backup.mkdir()

    result = run_cleanup(
        deploy_root=deployed,
        confirmation=(
            CLEANUP_CONFIRMATION
        ),
    )

    assert result == 1
    assert backup.exists()


def test_cleanup_rejects_wrong_confirmation(
    tmp_path,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    create_deployment(deployed)

    stage, backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260101T000000Z",
        )
    )

    result = run_cleanup(
        deploy_root=deployed,
        confirmation="WRONG",
    )

    assert result == 2
    assert stage.exists()
    assert backup.exists()


def test_cleanup_preserves_deployment_and_newest_backup(
    tmp_path,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    create_deployment(deployed)

    deployment_marker = (
        deployed / "live.txt"
    )
    deployment_marker.write_text(
        "untouched"
    )

    stage, backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260101T000000Z",
        )
    )

    backup_marker = (
        backup / "old.txt"
    ).read_text()

    result = run_cleanup(
        deploy_root=deployed,
        confirmation=(
            CLEANUP_CONFIRMATION
        ),
    )

    assert result == 0
    assert not stage.exists()
    assert deployed.exists()
    assert (
        deployment_marker.read_text()
        == "untouched"
    )
    assert backup.exists()
    assert (
        backup / "old.txt"
    ).read_text() == backup_marker
