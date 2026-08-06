import shutil
import subprocess
from pathlib import Path

from truepanel.upgrade.backup_receipt import (
    write_backup_receipt,
)
from truepanel.upgrade.promotion import (
    MANIFEST_NAME,
)
from truepanel.upgrade.rollback import (
    ROLLBACK_CONFIRMATION,
    build_rollback_plan,
    rollback_with_recovery,
    run_rollback,
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
    config: str,
) -> None:
    (root / "truepanel").mkdir(
        parents=True
    )
    (root / "qnaplcd").mkdir()

    (
        root
        / "truepanel"
        / "marker.txt"
    ).write_text(marker)

    (
        root / "truepanel.py"
    ).write_text(
        f"MARKER = {marker!r}\n"
    )

    (
        root / "truepanel.yaml"
    ).write_text(config)

    for filename in (
        "start-truepanel.sh",
        "deploy-truenas.sh",
        "pyproject.toml",
    ):
        (
            root / filename
        ).write_text(filename)


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


def add_receipt(
    backup: Path,
    deployed: Path,
) -> None:
    write_backup_receipt(
        backup_root=backup,
        deploy_root=deployed,
        source_root=deployed,
        kind="promotion",
    )


def marker(root: Path) -> str:
    return (
        root
        / "truepanel"
        / "marker.txt"
    ).read_text()


def test_successful_operator_rollback(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    selected = (
        tmp_path
        / ".truepanel-backup-selected"
    )
    safety = (
        tmp_path
        / ".truepanel-backup-rollback-test"
    )

    create_install(
        deployed,
        marker="current",
        config="theme_pack: tactical\n",
    )
    create_install(
        selected,
        marker="previous",
        config="theme_pack: default\n",
    )

    (
        deployed / ".venv"
    ).mkdir()
    (
        deployed
        / ".venv"
        / "runtime"
    ).write_text("preserved")

    selected.joinpath(
        "truepanel.yaml"
    ).unlink()
    add_receipt(
        selected,
        deployed,
    )

    runner = SandboxRsync()
    restart_calls = []

    plan = build_rollback_plan(
        deploy_root=deployed,
        selected_backup_root=selected,
        safety_backup_root=safety,
    )

    result = rollback_with_recovery(
        plan,
        runner=runner,
        restarter=lambda root: (
            restart_calls.append(root)
            or 0
        ),
        verifier=lambda root: (
            0
            if marker(root) == "previous"
            else 1
        ),
    )

    assert result == 0
    assert marker(deployed) == "previous"
    assert marker(safety) == "current"
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
    assert restart_calls == [
        deployed.resolve()
    ]


def test_failed_rollback_restores_current_state(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    selected = (
        tmp_path
        / ".truepanel-backup-selected"
    )
    safety = (
        tmp_path
        / ".truepanel-backup-rollback-test"
    )

    create_install(
        deployed,
        marker="current",
        config="theme_pack: tactical\n",
    )
    create_install(
        selected,
        marker="broken",
        config="theme_pack: default\n",
    )
    selected.joinpath(
        "truepanel.yaml"
    ).unlink()
    add_receipt(
        selected,
        deployed,
    )

    runner = SandboxRsync()
    restart_calls = []
    verify_calls = []

    def verifier(root):
        value = marker(root)
        verify_calls.append(value)

        return (
            0
            if value == "current"
            else 1
        )

    plan = build_rollback_plan(
        deploy_root=deployed,
        selected_backup_root=selected,
        safety_backup_root=safety,
    )

    result = rollback_with_recovery(
        plan,
        runner=runner,
        restarter=lambda root: (
            restart_calls.append(root)
            or 0
        ),
        verifier=verifier,
    )

    assert result == 1
    assert marker(deployed) == "current"
    assert verify_calls == [
        "broken",
        "current",
    ]
    assert restart_calls == [
        deployed.resolve(),
        deployed.resolve(),
    ]


def test_rollback_rejects_wrong_confirmation(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    selected = (
        tmp_path
        / ".truepanel-backup-selected"
    )

    create_install(
        deployed,
        marker="current",
        config="theme_pack: tactical\n",
    )
    create_install(
        selected,
        marker="previous",
        config="theme_pack: default\n",
    )

    calls = []

    result = run_rollback(
        deploy_root=deployed,
        selected_backup_root=selected,
        confirmation="WRONG",
        runner=lambda *args, **kwargs: (
            calls.append("runner")
        ),
        restarter=lambda root: (
            calls.append("restarter")
            or 0
        ),
        verifier=lambda root: (
            calls.append("verifier")
            or 0
        ),
    )

    assert result == 2
    assert calls == []
    assert marker(deployed) == "current"


def test_rollback_requires_explicit_backup(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"

    create_install(
        deployed,
        marker="current",
        config="theme_pack: tactical\n",
    )

    result = run_rollback(
        deploy_root=deployed,
        selected_backup_root=None,
        confirmation=(
            ROLLBACK_CONFIRMATION
        ),
    )

    assert result == 2


def test_rollback_rejects_backup_outside_parent(
    tmp_path,
):
    parent = tmp_path / "parent"
    outside = tmp_path / "outside"

    deployed = parent / "TruePanel"
    selected = (
        outside
        / ".truepanel-backup-selected"
    )

    create_install(
        deployed,
        marker="current",
        config="theme_pack: tactical\n",
    )
    create_install(
        selected,
        marker="previous",
        config="theme_pack: default\n",
    )

    try:
        build_rollback_plan(
            deploy_root=deployed,
            selected_backup_root=selected,
        )
    except ValueError as error:
        assert (
            "must be a sibling"
            in str(error)
        )
    else:
        raise AssertionError(
            "Unsafe backup was accepted"
        )


class PartialRestoreFailureRunner(
    SandboxRsync
):
    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def __call__(
        self,
        command,
        **kwargs,
    ):
        self.call_count += 1

        if self.call_count != 2:
            return super().__call__(
                command,
                **kwargs,
            )

        source = Path(
            command[-2].rstrip("/")
        )
        destination = Path(
            command[-1].rstrip("/")
        )

        partial_source = (
            source
            / "truepanel"
            / "marker.txt"
        )
        partial_destination = (
            destination
            / "truepanel"
            / "marker.txt"
        )

        partial_destination.write_text(
            partial_source.read_text()
        )

        return subprocess.CompletedProcess(
            command,
            23,
            "",
            "simulated partial restore failure",
        )


def test_partial_restore_failure_recovers_current_state(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    selected = (
        tmp_path
        / ".truepanel-backup-selected"
    )
    safety = (
        tmp_path
        / ".truepanel-backup-rollback-test"
    )

    create_install(
        deployed,
        marker="current",
        config="theme_pack: tactical\n",
    )
    create_install(
        selected,
        marker="previous",
        config="theme_pack: default\n",
    )

    selected.joinpath(
        "truepanel.yaml"
    ).unlink()
    add_receipt(
        selected,
        deployed,
    )

    runner = (
        PartialRestoreFailureRunner()
    )
    restart_calls = []
    verify_calls = []

    def verifier(root):
        value = marker(root)
        verify_calls.append(value)

        return (
            0
            if value == "current"
            else 1
        )

    plan = build_rollback_plan(
        deploy_root=deployed,
        selected_backup_root=selected,
        safety_backup_root=safety,
    )

    result = rollback_with_recovery(
        plan,
        runner=runner,
        restarter=lambda root: (
            restart_calls.append(root)
            or 0
        ),
        verifier=verifier,
    )

    assert result == 1
    assert marker(deployed) == "current"
    assert marker(safety) == "current"
    assert restart_calls == [
        deployed.resolve(),
    ]
    assert verify_calls == [
        "current",
    ]


class RecoveryFailureRunner(
    PartialRestoreFailureRunner
):
    def __call__(
        self,
        command,
        **kwargs,
    ):
        if self.call_count == 2:
            self.call_count += 1

            return subprocess.CompletedProcess(
                command,
                23,
                "",
                "simulated recovery failure",
            )

        return super().__call__(
            command,
            **kwargs,
        )


def test_partial_restore_and_recovery_failure_is_critical(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    selected = (
        tmp_path
        / ".truepanel-backup-selected"
    )
    safety = (
        tmp_path
        / ".truepanel-backup-rollback-test"
    )

    create_install(
        deployed,
        marker="current",
        config="theme_pack: tactical\n",
    )
    create_install(
        selected,
        marker="previous",
        config="theme_pack: default\n",
    )

    selected.joinpath(
        "truepanel.yaml"
    ).unlink()
    add_receipt(
        selected,
        deployed,
    )

    runner = RecoveryFailureRunner()

    plan = build_rollback_plan(
        deploy_root=deployed,
        selected_backup_root=selected,
        safety_backup_root=safety,
    )

    result = rollback_with_recovery(
        plan,
        runner=runner,
        restarter=lambda root: 0,
        verifier=lambda root: 0,
    )

    assert result == 2
    assert safety.exists()


def test_successful_rollback_does_not_copy_receipt_into_deployment(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    selected = (
        tmp_path
        / ".truepanel-backup-selected"
    )
    safety = (
        tmp_path
        / ".truepanel-backup-rollback-test"
    )

    create_install(
        deployed,
        marker="current",
        config="theme_pack: tactical\n",
    )
    create_install(
        selected,
        marker="previous",
        config="theme_pack: default\n",
    )

    selected.joinpath(
        "truepanel.yaml"
    ).unlink()

    add_receipt(
        selected,
        deployed,
    )

    plan = build_rollback_plan(
        deploy_root=deployed,
        selected_backup_root=selected,
        safety_backup_root=safety,
    )

    result = rollback_with_recovery(
        plan,
        runner=SandboxRsync(),
        restarter=lambda root: 0,
        verifier=lambda root: 0,
    )

    assert result == 0
    assert not (
        deployed
        / "truepanel-backup-receipt.json"
    ).exists()
    assert (
        selected
        / "truepanel-backup-receipt.json"
    ).is_file()
    assert (
        safety
        / "truepanel-backup-receipt.json"
    ).is_file()
