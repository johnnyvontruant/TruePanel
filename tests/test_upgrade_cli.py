from pathlib import Path

import pytest

from truepanel import cli


def test_parser_requires_upgrade_mode():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["upgrade"]
        )


def test_parser_accepts_upgrade_dry_run():
    args = cli.build_parser().parse_args(
        [
            "upgrade",
            "--dry-run",
        ]
    )

    assert args.command == "upgrade"
    assert args.dry_run is True
    assert args.stage_only is False


def test_parser_accepts_stage_only_options():
    args = cli.build_parser().parse_args(
        [
            "upgrade",
            "--source",
            "/source",
            "--root",
            "/deploy",
            "--stage-root",
            "/stage",
            "--stage-only",
        ]
    )

    assert args.upgrade_source == "/source"
    assert args.upgrade_root == "/deploy"
    assert args.upgrade_stage_root == "/stage"
    assert args.stage_only is True


def test_cli_dispatches_upgrade_before_plugins(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "upgrade",
            "--source",
            "/source",
            "--root",
            "/deploy",
            "--stage-root",
            "/stage",
            "--dry-run",
        ],
    )

    def fake_upgrade(**kwargs):
        captured.update(kwargs)
        return 7

    monkeypatch.setattr(
        cli,
        "run_upgrade",
        fake_upgrade,
    )

    monkeypatch.setattr(
        cli,
        "load_plugins",
        lambda: (_ for _ in ()).throw(
            AssertionError(
                "upgrade must not load plugins"
            )
        ),
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 7
    assert captured == {
        "source_root": Path("/source"),
        "deploy_root": Path("/deploy"),
        "stage_root": Path("/stage"),
        "dry_run": True,
        "stage_only": False,
    }


def test_parser_accepts_guarded_promotion():
    args = cli.build_parser().parse_args(
        [
            "upgrade",
            "--stage-root",
            "/stage",
            "--backup-root",
            "/backup",
            "--confirm",
            "PROMOTE_TRUEPANEL",
            "--promote",
        ]
    )

    assert args.promote is True
    assert (
        args.upgrade_stage_root
        == "/stage"
    )
    assert (
        args.upgrade_backup_root
        == "/backup"
    )
    assert (
        args.upgrade_confirmation
        == "PROMOTE_TRUEPANEL"
    )


def test_cli_dispatches_guarded_promotion(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "upgrade",
            "--root",
            "/deploy",
            "--stage-root",
            "/stage",
            "--backup-root",
            "/backup",
            "--confirm",
            "PROMOTE_TRUEPANEL",
            "--promote",
        ],
    )

    def fake_promotion(**kwargs):
        captured.update(kwargs)
        return 9

    import truepanel.upgrade

    monkeypatch.setattr(
        truepanel.upgrade,
        "run_promotion",
        fake_promotion,
    )

    with pytest.raises(
        SystemExit
    ) as error:
        cli.main()

    assert error.value.code == 9
    assert captured == {
        "stage_root": Path("/stage"),
        "deploy_root": Path("/deploy"),
        "backup_root": Path("/backup"),
        "confirmation": (
            "PROMOTE_TRUEPANEL"
        ),
    }
