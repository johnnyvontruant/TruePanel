import json

from truepanel.repair.checks import (
    files_differ,
    find_postinit_task,
    postinit_action,
    postinit_payload,
)


def test_postinit_payload_matches_truenas_contract(
    tmp_path,
):
    assert postinit_payload(
        tmp_path
    ) == {
        "type": "SCRIPT",
        "command": "",
        "script": str(
            tmp_path
            / "start-truepanel.sh"
        ),
        "when": "POSTINIT",
        "enabled": True,
        "timeout": 30,
        "comment": "TruePanel",
    }


def test_find_postinit_task_prefers_exact_script(
    tmp_path,
):
    expected = str(
        tmp_path
        / "start-truepanel.sh"
    )
    tasks = [
        {
            "id": 4,
            "comment": "TruePanel",
            "script": "/old/path/start.sh",
        },
        {
            "id": 8,
            "type": "SCRIPT",
            "script": expected,
        },
    ]

    task = find_postinit_task(
        tasks,
        tmp_path,
    )

    assert task is not None
    assert task["id"] == 8


def test_find_postinit_task_falls_back_to_comment(
    tmp_path,
):
    tasks = [
        {
            "id": 4,
            "comment": "TruePanel",
            "script": "/old/path/start.sh",
        }
    ]

    task = find_postinit_task(
        tasks,
        tmp_path,
    )

    assert task is not None
    assert task["id"] == 4


def test_postinit_action_creates_missing_task(
    tmp_path,
):
    action, task_id, payload = (
        postinit_action(
            [],
            tmp_path,
        )
    )

    assert action == "create"
    assert task_id is None
    assert payload["enabled"] is True


def test_postinit_action_updates_stale_task(
    tmp_path,
):
    action, task_id, payload = (
        postinit_action(
            [
                {
                    "id": 8,
                    "type": "SCRIPT",
                    "script": "/old/start.sh",
                    "when": "POSTINIT",
                    "enabled": False,
                    "timeout": 10,
                    "comment": "TruePanel",
                }
            ],
            tmp_path,
        )
    )

    assert action == "update"
    assert task_id == 8
    assert payload["script"] == str(
        tmp_path
        / "start-truepanel.sh"
    )


def test_postinit_action_skips_matching_task(
    tmp_path,
):
    payload = postinit_payload(
        tmp_path
    )
    task = {
        **payload,
        "id": 8,
    }

    action, task_id, returned = (
        postinit_action(
            [task],
            tmp_path,
        )
    )

    assert action == "none"
    assert task_id == 8
    assert returned == payload


def test_files_differ_detects_missing_file(
    tmp_path,
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_text("unit")

    assert files_differ(
        source,
        destination,
    ) is True


def test_files_differ_detects_matching_files(
    tmp_path,
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_text("unit")
    destination.write_text("unit")

    assert files_differ(
        source,
        destination,
    ) is False


def test_postinit_payload_is_json_serializable(
    tmp_path,
):
    encoded = json.dumps(
        postinit_payload(tmp_path)
    )

    assert "start-truepanel.sh" in encoded


def test_lifecycle_renderer_normalizes_environment_path(
    tmp_path,
):
    from truepanel.repair.checks import (
        generate_lifecycle_files,
    )

    root = tmp_path / "installation"
    root.mkdir()

    startup = root / "start-truepanel.sh"
    startup.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$TRUEPANEL_SYSTEMD_DIR"
mkdir -p "$TRUEPANEL_ENV_DIR"

cat > "$TRUEPANEL_ENV_DIR/truepanel-mission-control" <<EOF
TRUEPANEL_MC_PORT=8787
EOF

cat > "$TRUEPANEL_SYSTEMD_DIR/truepanel-mission-control.service" <<EOF
[Service]
EnvironmentFile=-$TRUEPANEL_ENV_DIR/truepanel-mission-control
EOF

cat > "$TRUEPANEL_SYSTEMD_DIR/truepanel.service" <<EOF
[Service]
ExecStart=truepanel
EOF
"""
    )
    startup.chmod(0o755)

    installed_env = (
        tmp_path / "etc-default"
    )

    sandbox, systemd_dir, env_dir, error = (
        generate_lifecycle_files(
            root,
            env_root=installed_env,
        )
    )

    try:
        assert error is None
        assert systemd_dir is not None
        assert env_dir is not None

        unit = (
            systemd_dir
            / "truepanel-mission-control.service"
        ).read_text()

        assert (
            f"EnvironmentFile=-{installed_env}/"
            "truepanel-mission-control"
            in unit
        )
        assert str(env_dir) not in unit
    finally:
        if sandbox is not None:
            sandbox.cleanup()
