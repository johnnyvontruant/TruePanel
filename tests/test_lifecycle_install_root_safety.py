import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_preview(script, install_root):
    return subprocess.run(
        [
            "bash",
            str(ROOT / script),
            "--dry-run",
            "--root",
            install_root,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_lifecycle_previews_accept_managed_path_below_pool():
    for script in ("install.sh", "uninstall.sh"):
        result = run_preview(
            script,
            "/mnt/TestPool/TruePanel",
        )

        assert result.returncode == 0, (
            script,
            result.stdout,
            result.stderr,
        )
        assert "/mnt/TestPool/TruePanel" in result.stdout


def test_lifecycle_previews_reject_pool_root():
    for script in ("install.sh", "uninstall.sh"):
        result = run_preview(
            script,
            "/mnt/TestPool",
        )

        assert result.returncode != 0
        assert (
            "may not be the pool root"
            in result.stderr
        )


def test_lifecycle_previews_reject_parent_escape_from_mnt():
    for script in ("install.sh", "uninstall.sh"):
        result = run_preview(
            script,
            "/mnt/../tmp/TruePanel",
        )

        assert result.returncode != 0
        assert "/tmp/TruePanel" in result.stderr
        assert (
            "must resolve below /mnt/<pool>/"
            in result.stderr
        )


def test_lifecycle_scripts_share_realpath_containment_contract():
    for script in ("install.sh", "uninstall.sh"):
        text = (ROOT / script).read_text(
            encoding="utf-8"
        )

        assert "normalize_install_root()" in text
        assert "Path(raw).expanduser().resolve(strict=False)" in text
        assert "len(parts) < 4" in text
        assert 'parts[1] != "mnt"' in text
        assert (
            'INSTALL_DIR="$(normalize_install_root '
            '"$INSTALL_DIR")"'
            in text
        )
