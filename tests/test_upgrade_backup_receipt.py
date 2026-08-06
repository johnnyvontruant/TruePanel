import json

import pytest

from truepanel.upgrade.backup_receipt import (
    BACKUP_RECEIPT_NAME,
    validate_backup_receipt,
    write_backup_receipt,
)


def test_backup_receipt_round_trip(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    backup = (
        tmp_path
        / ".truepanel-backup-test"
    )

    deployed.mkdir()
    backup.mkdir()

    receipt_path = write_backup_receipt(
        backup_root=backup,
        deploy_root=deployed,
        source_root=deployed,
        kind="promotion",
    )

    assert receipt_path == (
        backup / BACKUP_RECEIPT_NAME
    )

    payload = validate_backup_receipt(
        backup_root=backup,
        deploy_root=deployed,
    )

    assert payload["kind"] == "promotion"
    assert payload["state"] == "retained"


def test_receipt_rejects_wrong_backup_path(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    backup = (
        tmp_path
        / ".truepanel-backup-test"
    )

    deployed.mkdir()
    backup.mkdir()

    receipt_path = write_backup_receipt(
        backup_root=backup,
        deploy_root=deployed,
        source_root=deployed,
        kind="promotion",
    )

    payload = json.loads(
        receipt_path.read_text()
    )
    payload["backup_root"] = str(
        tmp_path
        / ".truepanel-backup-other"
    )
    receipt_path.write_text(
        json.dumps(payload)
    )

    with pytest.raises(
        ValueError,
        match="path does not match",
    ):
        validate_backup_receipt(
            backup_root=backup,
            deploy_root=deployed,
        )


def test_receipt_rejects_wrong_deployment(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    other = tmp_path / "OtherPanel"
    backup = (
        tmp_path
        / ".truepanel-backup-test"
    )

    deployed.mkdir()
    other.mkdir()
    backup.mkdir()

    write_backup_receipt(
        backup_root=backup,
        deploy_root=deployed,
        source_root=deployed,
        kind="rollback_safety",
    )

    with pytest.raises(
        ValueError,
        match="deployment does not match",
    ):
        validate_backup_receipt(
            backup_root=backup,
            deploy_root=other,
        )
