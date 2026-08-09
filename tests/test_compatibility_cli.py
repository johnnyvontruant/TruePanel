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


def test_parser_accepts_support_bundle():
    args = cli.build_parser().parse_args(
        [
            "compatibility",
            "--support-bundle",
        ]
    )

    assert args.compatibility_support_bundle is True
    assert args.compatibility_output is None


def test_parser_accepts_support_bundle_output():
    args = cli.build_parser().parse_args(
        [
            "compatibility",
            "--support-bundle",
            "--output",
            "/tmp/support.json",
        ]
    )

    assert args.compatibility_support_bundle is True
    assert (
        args.compatibility_output
        == "/tmp/support.json"
    )


def test_cli_passes_support_bundle_options(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "compatibility",
            "--support-bundle",
            "--output",
            "/tmp/support.json",
        ],
    )

    def fake_run(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        cli,
        "run_compatibility",
        fake_run,
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 0
    assert captured == {
        "json_output": False,
        "support_bundle": True,
        "output": "/tmp/support.json",
    }


def test_output_requires_support_bundle(
    monkeypatch,
):
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "truepanel",
            "compatibility",
            "--output",
            "/tmp/support.json",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
