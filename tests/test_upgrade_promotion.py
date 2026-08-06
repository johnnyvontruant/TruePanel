import json
import shutil
import subprocess
from pathlib import Path

from truepanel.upgrade.promotion import (
    MANIFEST_NAME,
    build_promotion_plan,
    promote_with_rollback,
)

PRESERVED_NAMES = {
    ".venv",
    "truepanel.yaml",
    MANIFEST_NAME,
}


def create_install(
    root: Path,
    *,
    marker: str,
    config: str,
):
    (root / "truepanel").mkdir(
        parents=True
    )
    (
        root
        / "truepanel"
        / "marker.txt"
    ).write_text(marker)
    (
        root
        / "truepanel.py"
    ).write_text(
        f"MARKER = {marker!r}\n"
    )
    (
        root
        / "truepanel.yaml"
    ).write_text(config)


def write_manifest(
    stage: Path,
    deployed: Path,
):
    (
        stage / MANIFEST_NAME
    ).write_text(
        json.dumps(
            {
                "state": "validated",
                "stage_root": str(
                    stage.resolve()
                ),
                "deploy_root": str(
                    deployed.resolve()
                ),
                "promotion_performed": False,
                "services_modified": False,
            }
        )
        + "\n"
    )


class FilesystemRunner:
    def __init__(self):
        self.commands = []

    def __call__(
        self,
        command,
        **kwargs,
    ):
        self.commands.append(
            list(command)
        )

        assert command[0] == "rsync"

        source = Path(
            command[-2].rstrip("/")
        )
        destination = Path(
            command[-1].rstrip("/")
        )

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        for item in list(
            destination.iterdir()
        ):
            if item.name in PRESERVED_NAMES:
                continue

            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        for item in source.iterdir():
            if item.name in PRESERVED_NAMES:
                continue

            target = destination / item.name

            if item.is_dir():
                shutil.copytree(
                    item,
                    target,
                )
            else:
                shutil.copy2(
                    item,
                    target,
                )

        return subprocess.CompletedProcess(
            command,
            0,
            "",
            "",
        )


def test_successful_promotion_preserves_runtime_state(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    stage = tmp_path / "stage"
    backup = tmp_path / "backup"

    create_install(
        deployed,
        marker="old",
        config="theme_pack: tactical\n",
    )
    create_install(
        stage,
        marker="new",
        config="theme_pack: default\n",
    )

    (
        deployed / ".venv"
    ).mkdir()

    runtime_marker = (
        deployed
        / ".venv"
        / "runtime"
    )
    runtime_marker.write_text(
        "preserved"
    )

    write_manifest(
        stage,
        deployed,
    )

    runner = FilesystemRunner()
    restart_calls = []

    plan = build_promotion_plan(
        stage_root=stage,
        deploy_root=deployed,
        backup_root=backup,
    )

    result = promote_with_rollback(
        plan,
        runner=runner,
        restarter=lambda root: (
            restart_calls.append(root)
            or 0
        ),
        verifier=lambda root: (
            0
            if (
                root
                / "truepanel"
                / "marker.txt"
            ).read_text()
            == "new"
            else 1
        ),
    )

    assert result == 0
    assert (
        deployed
        / "truepanel"
        / "marker.txt"
    ).read_text() == "new"
    assert (
        deployed / "truepanel.yaml"
    ).read_text() == (
        "theme_pack: tactical\n"
    )
    assert (
        runtime_marker.read_text()
        == "preserved"
    )
    assert (
        backup
        / "truepanel"
        / "marker.txt"
    ).read_text() == "old"
    assert restart_calls == [
        deployed.resolve()
    ]

    manifest = json.loads(
        (
            stage / MANIFEST_NAME
        ).read_text()
    )

    assert manifest["state"] == "promoted"
    assert (
        manifest["rollback_performed"]
        is False
    )
    assert manifest["backup_root"] == str(
        backup.resolve()
    )


def test_failed_verification_rolls_back(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    stage = tmp_path / "stage"
    backup = tmp_path / "backup"

    create_install(
        deployed,
        marker="old",
        config="theme_pack: tactical\n",
    )
    create_install(
        stage,
        marker="broken",
        config="theme_pack: default\n",
    )
    write_manifest(
        stage,
        deployed,
    )

    runner = FilesystemRunner()
    restart_calls = []
    verify_calls = []

    def verifier(root):
        marker = (
            root
            / "truepanel"
            / "marker.txt"
        ).read_text()

        verify_calls.append(marker)

        return (
            0
            if marker == "old"
            else 1
        )

    plan = build_promotion_plan(
        stage_root=stage,
        deploy_root=deployed,
        backup_root=backup,
    )

    result = promote_with_rollback(
        plan,
        runner=runner,
        restarter=lambda root: (
            restart_calls.append(root)
            or 0
        ),
        verifier=verifier,
    )

    assert result == 1
    assert verify_calls == [
        "broken",
        "old",
    ]
    assert restart_calls == [
        deployed.resolve(),
        deployed.resolve(),
    ]
    assert (
        deployed
        / "truepanel"
        / "marker.txt"
    ).read_text() == "old"
    assert (
        deployed / "truepanel.yaml"
    ).read_text() == (
        "theme_pack: tactical\n"
    )

    manifest = json.loads(
        (
            stage / MANIFEST_NAME
        ).read_text()
    )

    assert manifest["state"] == "rolled_back"
    assert (
        manifest["rollback_performed"]
        is True
    )


def test_rejects_unvalidated_stage(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    stage = tmp_path / "stage"

    create_install(
        deployed,
        marker="old",
        config="theme_pack: tactical\n",
    )
    create_install(
        stage,
        marker="new",
        config="theme_pack: tactical\n",
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
            }
        )
    )

    try:
        build_promotion_plan(
            stage_root=stage,
            deploy_root=deployed,
        )
    except ValueError as error:
        assert (
            "not in validated state"
            in str(error)
        )
    else:
        raise AssertionError(
            "Unvalidated stage was accepted"
        )
