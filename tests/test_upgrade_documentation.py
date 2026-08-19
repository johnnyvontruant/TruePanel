from pathlib import Path

INSTALLATION = Path("docs/INSTALLATION.md")
UPGRADING = Path("docs/UPGRADING.md")


def read(path):
    return path.read_text(
        encoding="utf-8"
    )


def test_installation_uses_lifecycle_upgrade():
    text = read(INSTALLATION)

    assert "truepanel verify --root /mnt/POOL/DATASET/TruePanel" in text
    assert "--dry-run" in text
    assert "guarded lifecycle manager" in text


def test_installation_rejects_old_develop_reinstall_flow():
    text = read(INSTALLATION)

    assert "git checkout develop" not in text
    assert "git pull --ff-only origin develop" not in text


def test_upgrade_guide_documents_full_sequence():
    text = read(UPGRADING)

    for term in (
        "## 1. Verify the current deployment",
        "## 3. Preview the upgrade",
        "## 4. Create and validate a staging tree",
        "## 5. Promote the validated stage",
        "## Upgrade cleanup",
        "## Operator-requested rollback",
        "## Repair",
    ):
        assert term in text


def test_upgrade_guide_documents_confirmations():
    text = read(UPGRADING)

    assert "PROMOTE_TRUEPANEL" in text
    assert "CLEAN_TRUEPANEL" in text
    assert "ROLLBACK_TRUEPANEL" in text


def test_upgrade_guide_documents_automatic_rollback():
    text = read(UPGRADING)

    assert (
        "automatically attempts to restore the "
        "pre-upgrade deployment"
        in text
    )

    assert (
        "not the same operation as an "
        "operator-requested rollback"
        in text
    )


def test_upgrade_guide_documents_rollback_safety_backup():
    text = read(UPGRADING)

    assert "pre-rollback safety backup" in text
    assert (
        "attempts to restore and verify the "
        "pre-rollback state"
        in text
    )


def test_upgrade_guide_documents_cleanup_preview():
    text = read(UPGRADING)

    assert "--cleanup" in text
    assert (
        "Without a confirmation phrase, cleanup "
        "reports the plan"
        in text
    )


def test_upgrade_guide_separates_repair_from_upgrade():
    text = read(UPGRADING)

    assert (
        "It is not an upgrade mechanism"
        in text
    )
    assert "truepanel repair" in text
    assert "--dry-run" in text


def test_upgrade_guide_does_not_teach_legacy_reinstall():
    text = read(UPGRADING)

    assert "git switch --detach v1.0.0" not in text
    assert "git switch --detach v0.9.0" not in text
    assert "bash install.sh" not in text


def test_upgrade_guide_documents_safe_backup_root():
    text = read(UPGRADING)

    assert "sibling of the deployment root" in text
    assert "`.truepanel-backup-`" in text
    assert (
        "/mnt/POOL/DATASET/"
        ".truepanel-backup-TruePanel-before-v1.2.0-rc3"
        in text
    )
    assert (
        "before any deployment files are copied"
        in text
    )

def test_upgrade_guide_documents_promotion_runtime_ownership():
    text = read(UPGRADING)

    assert "Installer-owned `bin/` artifacts" in text
    assert "`bin/truepanel`" in text
    assert (
        "Backup creation and rollback continue to copy "
        "these artifacts"
        in text
    )
    assert (
        "deployed generation's own `.venv/bin/python` "
        "and `truepanel.py`"
        in text
    )
    assert (
        "Only transient Mission Control or LCD "
        "readiness failures are retried"
        in text
    )
