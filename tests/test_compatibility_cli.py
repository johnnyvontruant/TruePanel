import pytest

from truepanel import cli


def test_parser_accepts_compatibility():
    args = cli.build_parser().parse_args(
        ["compatibility"]
    )

    assert args.command == "compatibility"
    assert args.compatibility_json is False


def test_parser_accepts_compatibility_json():
    args = cli.build_parser().parse_args(
        [
            "compatibility",
            "--json",
        ]
    )

    assert args.command == "compatibility"
    assert args.compatibility_json is True


def test_cli_dispatches_compatibility_before_plugins(
    monkeypatch,
):
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "compatibility",
        ],
    )

    monkeypatch.setattr(
        cli,
        "run_compatibility",
        lambda **kwargs: 7,
    )

    def fail_plugin_load():
        raise AssertionError(
            "compatibility must not load plugins"
        )

    monkeypatch.setattr(
        cli,
        "load_plugins",
        fail_plugin_load,
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 7
