import json
import shutil
import subprocess
from pathlib import Path

import pytest

from truepanel import cli
from truepanel.upgrade.promotion import (
    MANIFEST_NAME,
    run_promotion,
)

PRESERVED_NAMES = {
    ".venv",
    "truepanel.yaml",
    MANIFEST_NAME,
    "truepanel-backup-receipt.json",
}


def create_install(
    root: Path,
    *,
    marker: str,
    config: str = "theme_pack: tactical\n",
) -> None:
    (root / "truepanel").mkdir(
        parents=True
    )

    (
        root
        / "truepanel"
        / "marker.txt"
    ).write_text(
        marker
    )

    (
        root / "truepanel.py"
    ).write_text(
        f"MARKER = {marker!r}\n"
    )

    (
        root / "truepanel.yaml"
    ).write_text(
        config
    )


def create_manifest(
    stage: Path,
    deployed: Path,
) -> None:
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


class SandboxRsync:
    def __init__(self) -> None:
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

            target = (
                destination / item.name
            )

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


def test_cli_successful_sandbox_promotion(
    tmp_path,
    monkeypatch,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    stage = tmp_path / "stage"
    backup = (
        tmp_path
        / ".truepanel-backup-test"
    )

    create_install(
        deployed,
        marker="old",
    )
    create_install(
        stage,
        marker="new",
        config="theme_pack: default\n",
    )

    (
        deployed / ".venv"
    ).mkdir()

    (
        deployed
        / ".venv"
        / "runtime"
    ).write_text(
        "preserved"
    )

    create_manifest(
        stage,
        deployed,
    )

    runner = SandboxRsync()
    restart_calls = []

    def sandbox_promotion(
        **kwargs,
    ):
        return run_promotion(
            **kwargs,
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

    import truepanel.upgrade

    monkeypatch.setattr(
        truepanel.upgrade,
        "run_promotion",
        sandbox_promotion,
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "upgrade",
            "--root",
            str(deployed),
            "--stage-root",
            str(stage),
            "--backup-root",
            str(backup),
            "--confirm",
            "PROMOTE_TRUEPANEL",
            "--promote",
        ],
    )

    with pytest.raises(
        SystemExit
    ) as error:
        cli.main()

    assert error.value.code == 0

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
        deployed
        / ".venv"
        / "runtime"
    ).read_text() == "preserved"

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

    assert (
        manifest["state"]
        == "promoted"
    )

    assert (
        manifest["rollback_performed"]
        is False
    )


def test_cli_failed_verification_rolls_back(
    tmp_path,
    monkeypatch,
):
    deployed = (
        tmp_path / "TruePanel"
    )
    stage = tmp_path / "stage"
    backup = (
        tmp_path
        / ".truepanel-backup-test"
    )

    create_install(
        deployed,
        marker="old",
    )
    create_install(
        stage,
        marker="broken",
    )

    create_manifest(
        stage,
        deployed,
    )

    runner = SandboxRsync()
    restart_calls = []
    verify_calls = []

    def verifier(root):
        marker = (
            root
            / "truepanel"
            / "marker.txt"
        ).read_text()

        verify_calls.append(
            marker
        )

        return (
            0
            if marker == "old"
            else 1
        )

    def sandbox_promotion(
        **kwargs,
    ):
        return run_promotion(
            **kwargs,
            runner=runner,
            restarter=lambda root: (
                restart_calls.append(root)
                or 0
            ),
            verifier=verifier,
        )

    import truepanel.upgrade

    monkeypatch.setattr(
        truepanel.upgrade,
        "run_promotion",
        sandbox_promotion,
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "upgrade",
            "--root",
            str(deployed),
            "--stage-root",
            str(stage),
            "--backup-root",
            str(backup),
            "--confirm",
            "PROMOTE_TRUEPANEL",
            "--promote",
        ],
    )

    with pytest.raises(
        SystemExit
    ) as error:
        cli.main()

    assert error.value.code == 1

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

    manifest = json.loads(
        (
            stage / MANIFEST_NAME
        ).read_text()
    )

    assert (
        manifest["state"]
        == "rolled_back"
    )

    assert (
        manifest["rollback_performed"]
        is True
    )
