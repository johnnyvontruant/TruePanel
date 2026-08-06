from pathlib import Path

import pytest

from truepanel import cli


def test_parser_accepts_verify():
    args = cli.build_parser().parse_args(
        ["verify"]
    )

    assert args.command == "verify"


def test_cli_dispatches_verify_before_plugins(
    monkeypatch,
):
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["truepanel", "verify"],
    )
    monkeypatch.setattr(
        cli,
        "run_verify",
        lambda **kwargs: 7,
    )

    def fail_plugin_load():
        raise AssertionError(
            "verify must not load plugins"
        )

    monkeypatch.setattr(
        cli,
        "load_plugins",
        fail_plugin_load,
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 7



def test_parser_accepts_verify_root():
    args = cli.build_parser().parse_args(
        [
            "verify",
            "--root",
            "/srv/truepanel",
        ]
    )

    assert args.command == "verify"
    assert args.verify_root == "/srv/truepanel"


def test_cli_passes_explicit_verify_root(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "verify",
            "--root",
            "/srv/truepanel",
        ],
    )

    def fake_verify(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        cli,
        "run_verify",
        fake_verify,
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 0
    assert captured["root"] == Path(
        "/srv/truepanel"
    )
