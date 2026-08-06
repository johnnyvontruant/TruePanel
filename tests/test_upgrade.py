import json
import subprocess
from pathlib import Path

from truepanel.upgrade.checks import (
    RSYNC_EXCLUDES,
    build_plan,
    prepare_stage,
    rsync_command,
)


def create_tree(
    root: Path,
    *,
    version: str,
    config: str = "theme_pack: tactical\n",
):
    (root / "truepanel").mkdir(
        parents=True
    )
    (root / "qnaplcd").mkdir()

    (
        root
        / "truepanel"
        / "__init__.py"
    ).write_text(
        f'__version__ = "{version}"\n'
    )
    (
        root
        / "qnaplcd"
        / "__init__.py"
    ).write_text("")
    (root / "truepanel.py").write_text(
        "print('launcher')\n"
    )
    (root / "collector.py").write_text("")
    (root / "lcd-menu.py").write_text("")
    (
        root
        / "mission_control_web.py"
    ).write_text("")
    (
        root
        / "start-truepanel.sh"
    ).write_text("#!/bin/bash\n")
    (
        root
        / "deploy-truenas.sh"
    ).write_text("#!/bin/bash\n")
    (
        root
        / "pyproject.toml"
    ).write_text(
        "[project]\n"
        f'version = "{version}"\n'
    )
    (
        root
        / "truepanel.yaml"
    ).write_text(config)


def test_plan_uses_sibling_stage(
    tmp_path,
):
    source = tmp_path / "source"
    deployed = tmp_path / "TruePanel"

    create_tree(
        source,
        version="1.2.0",
    )
    create_tree(
        deployed,
        version="1.1.0",
    )

    (
        deployed
        / ".venv"
        / "bin"
    ).mkdir(
        parents=True
    )
    python = (
        deployed
        / ".venv"
        / "bin"
        / "python"
    )
    python.write_text("")

    plan = build_plan(
        source_root=source,
        deploy_root=deployed,
    )

    assert plan.source_version == "1.2.0"
    assert plan.deployed_version == "1.1.0"
    assert Path(
        plan.stage_root
    ).parent == deployed.parent
    assert (
        ".venv/"
        in plan.exclusions
    )
    assert (
        "truepanel.yaml"
        in plan.exclusions
    )

    for exclusion in (
        "development/logs/",
        "development/backups/",
        "development/firmware/",
    ):
        assert exclusion in plan.exclusions


def test_rsync_contract_preserves_runtime_state(
    tmp_path,
):
    source = tmp_path / "source"
    deployed = tmp_path / "deployed"
    stage = tmp_path / "stage"

    create_tree(
        source,
        version="1.2.0",
    )
    create_tree(
        deployed,
        version="1.1.0",
    )

    plan = build_plan(
        source_root=source,
        deploy_root=deployed,
        stage_root=stage,
    )
    command = rsync_command(plan)

    assert command[:3] == [
        "rsync",
        "-a",
        "--delete",
    ]

    for exclusion in RSYNC_EXCLUDES:
        assert (
            f"--exclude={exclusion}"
            in command
        )


def test_stage_copies_deployed_configuration(
    tmp_path,
):
    source = tmp_path / "source"
    deployed = tmp_path / "deployed"
    stage = tmp_path / "stage"

    create_tree(
        source,
        version="1.2.0",
        config="theme_pack: default\n",
    )
    create_tree(
        deployed,
        version="1.1.0",
        config="theme_pack: tactical\n",
    )

    plan = build_plan(
        source_root=source,
        deploy_root=deployed,
        stage_root=stage,
    )

    def runner(
        command,
        **kwargs,
    ):
        if command[0] == "rsync":
            for item in source.iterdir():
                if item.name in (
                    ".venv",
                    "truepanel.yaml",
                ):
                    continue

                destination = (
                    stage / item.name
                )

                if item.is_dir():
                    import shutil

                    shutil.copytree(
                        item,
                        destination,
                    )
                else:
                    import shutil

                    shutil.copy2(
                        item,
                        destination,
                    )

        return subprocess.CompletedProcess(
            command,
            0,
            "",
            "",
        )

    ok, detail = prepare_stage(
        plan,
        runner=runner,
    )

    assert ok is True
    assert detail == str(stage)
    assert (
        stage
        / "truepanel.yaml"
    ).read_text() == (
        "theme_pack: tactical\n"
    )

    manifest = json.loads(
        (
            stage
            / "truepanel-upgrade-manifest.json"
        ).read_text()
    )

    assert manifest["state"] == "validated"
    assert (
        manifest["promotion_performed"]
        is False
    )
    assert (
        manifest["services_modified"]
        is False
    )
