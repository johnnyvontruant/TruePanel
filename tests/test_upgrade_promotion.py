import json
import shutil
import subprocess
from pathlib import Path

from truepanel.upgrade.promotion import (
    MANIFEST_NAME,
    PROMOTION_DEPLOY_EXCLUDES,
    build_promotion_plan,
    ensure_cli_wrapper,
    promote_with_rollback,
    sync_command,
    verify_truepanel,
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
    backup = (
        tmp_path
        / ".truepanel-backup-test"
    )

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

    wrapper = (
        deployed / "bin" / "truepanel"
    )
    assert wrapper.is_file()
    assert wrapper.stat().st_mode & 0o111

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
    backup = (
        tmp_path
        / ".truepanel-backup-test"
    )

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
    assert not (
        deployed / "bin" / "truepanel"
    ).exists()
    assert not (
        backup / "bin" / "truepanel"
    ).exists()

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


def test_promotion_rejects_wrong_confirmation(
    tmp_path,
):
    from truepanel.upgrade.promotion import (
        run_promotion,
    )

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
    write_manifest(
        stage,
        deployed,
    )

    result = run_promotion(
        stage_root=stage,
        deploy_root=deployed,
        confirmation="NOPE",
        restarter=lambda root: 0,
        verifier=lambda root: 0,
    )

    assert result == 2
    assert (
        deployed
        / "truepanel"
        / "marker.txt"
    ).read_text() == "old"


def test_promotion_requires_explicit_stage(
    tmp_path,
):
    from truepanel.upgrade.promotion import (
        run_promotion,
    )

    deployed = tmp_path / "TruePanel"

    create_install(
        deployed,
        marker="old",
        config="theme_pack: tactical\n",
    )

    result = run_promotion(
        stage_root=None,
        deploy_root=deployed,
        confirmation="PROMOTE_TRUEPANEL",
        restarter=lambda root: 0,
        verifier=lambda root: 0,
    )

    assert result == 2


def test_rejected_confirmation_invokes_nothing(
    tmp_path,
):
    from truepanel.upgrade.promotion import (
        run_promotion,
    )

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
    write_manifest(
        stage,
        deployed,
    )

    calls = []

    def forbidden_runner(*args, **kwargs):
        calls.append("runner")
        raise AssertionError(
            "runner must not be called"
        )

    def forbidden_restarter(root):
        calls.append("restarter")
        raise AssertionError(
            "restarter must not be called"
        )

    def forbidden_verifier(root):
        calls.append("verifier")
        raise AssertionError(
            "verifier must not be called"
        )

    result = run_promotion(
        stage_root=stage,
        deploy_root=deployed,
        confirmation="WRONG",
        runner=forbidden_runner,
        restarter=forbidden_restarter,
        verifier=forbidden_verifier,
    )

    assert result == 2
    assert calls == []


def test_promotion_rejects_unsafe_backup_before_copy(
    tmp_path,
):
    from truepanel.upgrade.promotion import (
        run_promotion,
    )

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
        config="theme_pack: default\n",
    )
    write_manifest(
        stage,
        deployed,
    )

    invalid_backups = (
        tmp_path / "TruePanel-unsafe-backup",
        (
            tmp_path
            / "outside"
            / ".truepanel-backup-test"
        ),
    )

    for backup in invalid_backups:
        calls = []

        def forbidden_runner(
            *args,
            calls=calls,
            **kwargs,
        ):
            calls.append("runner")
            raise AssertionError(
                "backup copy must not begin"
            )

        result = run_promotion(
            stage_root=stage,
            deploy_root=deployed,
            backup_root=backup,
            confirmation="PROMOTE_TRUEPANEL",
            runner=forbidden_runner,
            restarter=lambda root: 0,
            verifier=lambda root: 0,
        )

        assert result == 1
        assert calls == []
        assert not backup.exists()
        assert (
            deployed
            / "truepanel"
            / "marker.txt"
        ).read_text() == "old"
def test_promotion_bin_exclusion_is_deploy_only(
    tmp_path,
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"

    assert "--exclude=bin/" not in sync_command(
        source,
        destination,
    )
    assert "--exclude=bin/" in sync_command(
        source,
        destination,
        extra_excludes=PROMOTION_DEPLOY_EXCLUDES,
    )


def _verify_runtime(root):
    python_path = (
        root / ".venv" / "bin" / "python"
    )
    python_path.parent.mkdir(
        parents=True
    )
    python_path.write_text(
        "python\n"
    )

    launcher = root / "truepanel.py"
    launcher.write_text(
        "launcher\n"
    )

    return python_path, launcher


def test_verify_truepanel_uses_deployed_generation(
    tmp_path,
):
    root = tmp_path / "TruePanel"
    python_path, launcher = (
        _verify_runtime(root)
    )
    calls = []

    def runner(command, **kwargs):
        calls.append(
            (
                list(command),
                kwargs,
            )
        )
        return subprocess.CompletedProcess(
            command,
            0,
            "Verification Result\nPASS\n",
            "",
        )

    assert verify_truepanel(
        root,
        runner=runner,
        sleeper=lambda delay: None,
    ) == 0
    assert calls[0][0] == [
        str(python_path.resolve()),
        str(launcher.resolve()),
        "verify",
        "--root",
        str(root.resolve()),
    ]
    assert calls[0][1]["timeout"] == 120.0


def test_verify_truepanel_retries_transient_readiness(
    tmp_path,
):
    root = tmp_path / "TruePanel"
    _verify_runtime(root)
    sleeps = []
    calls = []
    responses = [
        subprocess.CompletedProcess(
            ["verify"],
            1,
            (
                "FAIL  LCD transport                  "
                "port=/dev/ttyS1 baud=1200 errors=0\n"
            ),
            "",
        ),
        subprocess.CompletedProcess(
            ["verify"],
            0,
            "Verification Result\nPASS\n",
            "",
        ),
    ]

    def runner(command, **_kwargs):
        calls.append(
            list(command)
        )
        return responses.pop(0)

    assert verify_truepanel(
        root,
        runner=runner,
        sleeper=sleeps.append,
        attempts=3,
        retry_delay=0.25,
    ) == 0
    assert len(calls) == 2
    assert sleeps == [0.25]


def test_verify_truepanel_does_not_retry_real_failure(
    tmp_path,
):
    root = tmp_path / "TruePanel"
    _verify_runtime(root)
    sleeps = []
    calls = []

    def runner(command, **_kwargs):
        calls.append(
            list(command)
        )
        return subprocess.CompletedProcess(
            command,
            1,
            (
                "FAIL  Package version                "
                "Runtime=1.2.0rc1; deployment metadata differs\n"
                "FAIL  LCD transport                  "
                "port=/dev/ttyS1 baud=1200 errors=0\n"
            ),
            "",
        )

    assert verify_truepanel(
        root,
        runner=runner,
        sleeper=sleeps.append,
        attempts=3,
        retry_delay=0.25,
    ) == 1
    assert len(calls) == 1
    assert sleeps == []


def test_ensure_cli_wrapper_bootstraps_legacy_deployment(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    deployed.mkdir()

    success, detail = ensure_cli_wrapper(
        deployed
    )

    wrapper = (
        deployed / "bin" / "truepanel"
    )

    assert success is True
    assert detail == str(wrapper)
    assert wrapper.read_text(
        encoding="utf-8"
    ) == (
        "#!/usr/bin/env bash\n"
        f'cd "{deployed}"\n'
        f'exec "{deployed}/.venv/bin/python" '
        f'"{deployed}/truepanel.py" "$@"\n'
    )
    assert wrapper.stat().st_mode & 0o111


def test_ensure_cli_wrapper_preserves_existing_wrapper(
    tmp_path,
):
    deployed = tmp_path / "TruePanel"
    wrapper = (
        deployed / "bin" / "truepanel"
    )
    wrapper.parent.mkdir(
        parents=True
    )
    wrapper.write_text(
        "managed wrapper\n",
        encoding="utf-8",
    )

    success, detail = ensure_cli_wrapper(
        deployed
    )

    assert success is True
    assert detail == str(wrapper)
    assert wrapper.read_text(
        encoding="utf-8"
    ) == "managed wrapper\n"
