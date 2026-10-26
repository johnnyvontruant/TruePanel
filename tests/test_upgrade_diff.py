import subprocess
from pathlib import Path

from truepanel.upgrade.checks import run_upgrade
from truepanel.upgrade.diff import content_changes, diff_command, parse_itemized

ITEMIZED = """\
>f+++++++++ truepanel/loadmaster/identity.py
>fcst...... truepanel/loadmaster/plan.py
>f..t...... docs/LOADMASTER.md
cd+++++++++ truepanel/new_package/
*deleting   loadmaster-observer-scheduled.sh
*deleting   truepanel/cargo/
"""


def done(stdout="", code=0):
    return subprocess.CompletedProcess(["rsync"], code, stdout, "boom" if code else "")


def test_itemized_output_is_grouped():
    changes = parse_itemized(ITEMIZED)
    assert changes.added == ["truepanel/loadmaster/identity.py"]
    assert changes.changed == ["truepanel/loadmaster/plan.py", "docs/LOADMASTER.md"]
    assert changes.deleted == ["loadmaster-observer-scheduled.sh"]
    assert changes.total == 4


def test_diff_uses_the_promotion_excludes_and_checksums():
    command = diff_command(Path("/stage"), Path("/deploy"))
    assert command[:6] == ["rsync", "-n", "-a", "-c", "--delete", "--itemize-changes"]
    assert "--exclude=truepanel.yaml" in command and "--exclude=bin/" in command
    assert "--exclude=truepanel-build.json" in command  # staging writes a fresh one
    assert command[-2:] == ["/stage/", "/deploy/"]


def test_diff_failure_is_reported_not_raised():
    changes, error = content_changes(
        Path("/a"), Path("/b"), runner=lambda *a, **k: done(code=23)
    )
    assert changes is None and "boom" in error

    def broken(*args, **kwargs):
        raise subprocess.TimeoutExpired("rsync", 600)

    assert content_changes(Path("/a"), Path("/b"), runner=broken)[0] is None


def make_tree(root: Path, version: str) -> None:
    (root / "truepanel").mkdir(parents=True)
    (root / "truepanel" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    for name in (
        "truepanel.py",
        "start-truepanel.sh",
        "deploy-truenas.sh",
        "pyproject.toml",
    ):
        (root / name).write_text("")
    (root / "truepanel.yaml").write_text("theme_pack: tactical\n")


def test_dry_run_lists_what_promotion_would_change(tmp_path, capsys):
    source, deployed = tmp_path / "source", tmp_path / "TruePanel"
    make_tree(source, "1.3.1rc1")
    make_tree(deployed, "1.3.1rc1")

    result = run_upgrade(
        source_root=source,
        deploy_root=deployed,
        dry_run=True,
        diff_runner=lambda *a, **k: done(ITEMIZED),
    )

    out = capsys.readouterr().out
    assert result == 0
    assert "2 changed, 1 added, 1 deleted" in out
    assert "deleted  loadmaster-observer-scheduled.sh" in out
    assert "DRY RUN COMPLETE" in out
