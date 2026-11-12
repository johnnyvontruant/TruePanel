import shutil
import subprocess
import sys
from pathlib import Path

from test_upgrade import create_tree

from truepanel.upgrade.checks import build_plan, prepare_stage
from truepanel.upgrade.smoke import command

REPO = Path(__file__).resolve().parent.parent


def smoke(stage: Path, config: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        command(Path(sys.executable), stage, config),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def copy_tree(tmp_path: Path) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("truepanel", "qnaplcd"):
        shutil.copytree(
            REPO / name, stage / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copy2(REPO / "truepanel.yaml", stage / "truepanel.yaml")
    return stage


def test_the_repository_passes_its_own_smoke_test(tmp_path):
    stage = copy_tree(tmp_path)
    result = smoke(stage, stage / "truepanel.yaml")
    assert result.returncode == 0, result.stderr


def test_a_module_that_fails_to_import_is_caught(tmp_path):
    stage = copy_tree(tmp_path)
    with (stage / "truepanel" / "loadmaster" / "sounds.py").open("a") as handle:
        handle.write("\nimport module_that_does_not_exist\n")
    result = smoke(stage, stage / "truepanel.yaml")
    assert result.returncode == 1
    assert "import truepanel.loadmaster: ModuleNotFoundError" in result.stderr


def test_a_config_the_new_code_rejects_is_caught(tmp_path):
    stage = copy_tree(tmp_path)
    config = stage / "truepanel.yaml"
    config.write_text(
        config.read_text().replace(
            "  enabled: false\n  state_dir:",
            "  enabled: true\n  sounds: loud\n  state_dir:",
            1,
        )
    )
    result = smoke(stage, config)
    assert result.returncode == 1
    assert "LoadmasterConfigError" in result.stderr


def test_staging_fails_and_removes_the_stage_when_the_smoke_test_fails(tmp_path):
    source, deployed, stage = (
        tmp_path / "source",
        tmp_path / "deployed",
        tmp_path / "stage",
    )
    create_tree(source, version="1.2.0")
    create_tree(deployed, version="1.1.0")
    plan = build_plan(source_root=source, deploy_root=deployed, stage_root=stage)

    def runner(cmd, **kwargs):
        if cmd[0] == "rsync":
            shutil.copytree(
                source,
                stage,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".venv"),
            )
        if "-P" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "import truepanel.x: boom")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    ok, detail = prepare_stage(plan, runner=runner)
    assert ok is False
    assert detail == "Staged smoke test failed: import truepanel.x: boom"
    assert not stage.exists()
