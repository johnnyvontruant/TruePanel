from pathlib import Path

from truepanel.upgrade.checks import (
    RSYNC_EXCLUDES,
    UpgradePlan,
    rsync_command,
)
from truepanel.upgrade.promotion import sync_command


def _plan(tmp_path: Path) -> UpgradePlan:
    return UpgradePlan(
        source_root=str(tmp_path / "source"),
        deploy_root=str(tmp_path / "deploy"),
        stage_root=str(tmp_path / "stage"),
        source_version="1.2.0",
        deployed_version="1.2.0rc3",
        python_path="/usr/bin/python3",
        exclusions=RSYNC_EXCLUDES,
    )


def test_stage_excludes_git_metadata_file_or_directory(tmp_path):
    assert ".git" in RSYNC_EXCLUDES
    assert ".git/" not in RSYNC_EXCLUDES

    command = rsync_command(
        _plan(tmp_path)
    )

    assert "--exclude=.git" in command
    assert "--exclude=.git/" not in command


def test_promotion_inherits_git_metadata_exclusion(tmp_path):
    command = sync_command(
        tmp_path / "source",
        tmp_path / "deploy",
    )

    assert "--exclude=.git" in command
    assert "--exclude=.git/" not in command
