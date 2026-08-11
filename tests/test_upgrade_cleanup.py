import json
from pathlib import Path

from truepanel.upgrade.backup_receipt import (
    write_backup_receipt,
)
from truepanel.upgrade.cleanup import (
    CLEANUP_CONFIRMATION,
    backup_content_identity,
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


def test_cleanup_keeps_two_distinct_generations(
    tmp_path,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    create_deployment(deployed)

    oldest_stage, oldest_backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260101T000000Z",
        )
    )

    middle_stage, middle_backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260102T000000Z",
        )
    )

    newest_stage, newest_backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260103T000000Z",
        )
    )

    plan = build_cleanup_plan(
        deploy_root=deployed,
    )

    actions = {
        asset.path: asset.action
        for asset in plan.assets
    }

    assert actions[oldest_stage] == "remove"
    assert actions[middle_stage] == "remove"
    assert actions[newest_stage] == "remove"

    assert actions[oldest_backup] == "remove"
    assert actions[middle_backup] == "keep"
    assert actions[newest_backup] == "keep"

def test_cleanup_generation_order_is_deterministic_for_equal_mtimes(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    create_deployment(deployed)

    oldest_stage, oldest_backup = create_completed_upgrade(
        tmp_path,
        deployed,
        token="20260101T000000Z",
    )
    middle_stage, middle_backup = create_completed_upgrade(
        tmp_path,
        deployed,
        token="20260102T000000Z",
    )
    newest_stage, newest_backup = create_completed_upgrade(
        tmp_path,
        deployed,
        token="20260103T000000Z",
    )

    equal_mtime = 1_700_000_000

    for path in (
        oldest_stage,
        middle_stage,
        newest_stage,
        oldest_backup,
        middle_backup,
        newest_backup,
    ):
        path.touch()
        path.chmod(path.stat().st_mode)
        import os
        os.utime(
            path,
            (
                equal_mtime,
                equal_mtime,
            ),
        )

    plan = build_cleanup_plan(
        deploy_root=deployed,
    )

    actions = {
        asset.path: asset.action
        for asset in plan.assets
    }

    assert actions[oldest_backup] == "remove"
    assert actions[middle_backup] == "keep"
    assert actions[newest_backup] == "keep"


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


def test_cleanup_removes_duplicate_generation(
    tmp_path,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    create_deployment(deployed)

    first_stage, first_backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260101T000000Z",
        )
    )

    second_stage, second_backup = (
        create_completed_upgrade(
            tmp_path,
            deployed,
            token="20260102T000000Z",
        )
    )

    (
        first_backup / "old.txt"
    ).write_text("identical")

    (
        second_backup / "old.txt"
    ).write_text("identical")

    first_stage.touch()
    first_backup.touch()
    second_stage.touch()
    second_backup.touch()

    plan = build_cleanup_plan(
        deploy_root=deployed,
    )

    actions = {
        asset.path: asset.action
        for asset in plan.assets
    }

    kept = {
        path
        for path in (
            first_backup,
            second_backup,
        )
        if actions[path] == "keep"
    }

    removed = {
        path
        for path in (
            first_backup,
            second_backup,
        )
        if actions[path] == "remove"
    }

    assert len(kept) == 1
    assert len(removed) == 1


def test_backup_identity_ignores_empty_and_cache_directories(
    tmp_path,
):
    backup = (
        tmp_path
        / ".truepanel-backup-test"
    )

    (
        backup
        / "truepanel"
    ).mkdir(
        parents=True,
    )

    (
        backup
        / "truepanel"
        / "runtime.py"
    ).write_text(
        "meaningful content\n"
    )

    identity_before = (
        backup_content_identity(
            backup
        )
    )

    (
        backup
        / "truepanel"
        / "upgrade"
    ).mkdir(
        parents=True,
    )

    cache = (
        backup
        / "truepanel"
        / "__pycache__"
    )
    cache.mkdir(
        parents=True,
    )

    (
        cache
        / "runtime.cpython-311.pyc"
    ).write_bytes(
        b"runtime cache"
    )

    identity_after = (
        backup_content_identity(
            backup
        )
    )

    assert identity_after == identity_before
