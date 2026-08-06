from pathlib import Path

import pytest

from truepanel import cli


def test_parser_accepts_repair():
    args = cli.build_parser().parse_args(
        ["repair"]
    )

    assert args.command == "repair"
    assert args.repair_root is None
    assert args.dry_run is False


def test_parser_accepts_repair_options():
    args = cli.build_parser().parse_args(
        [
            "repair",
            "--root",
            "/srv/truepanel",
            "--dry-run",
        ]
    )

    assert args.repair_root == (
        "/srv/truepanel"
    )
    assert args.dry_run is True


def test_cli_dispatches_repair_before_plugins(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "repair",
            "--root",
            "/srv/truepanel",
            "--dry-run",
        ],
    )

    def fake_repair(**kwargs):
        captured.update(kwargs)
        return 6

    monkeypatch.setattr(
        cli,
        "run_repair",
        fake_repair,
    )

    def fail_plugin_load():
        raise AssertionError(
            "repair must not load plugins"
        )

    monkeypatch.setattr(
        cli,
        "load_plugins",
        fail_plugin_load,
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 6
    assert captured == {
        "root": Path(
            "/srv/truepanel"
        ),
        "dry_run": True,
    }
