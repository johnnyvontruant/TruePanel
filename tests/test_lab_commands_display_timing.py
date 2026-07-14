from contextlib import contextmanager
from pathlib import Path

from truepanel.lab.commands import (
    build_parser,
    main,
    run_display_timing,
)


class FakeController:
    def __init__(self):
        self.calls = []

    def clear(self):
        self.calls.append(("clear",))

    def write_text(self, row, text):
        self.calls.append(("write_text", row, text))

    def write_frame(self, line1, line2):
        self.calls.append(("write_frame", line1, line2))


CONTROLLER = FakeController()


@contextmanager
def fake_open_controller(*args, **kwargs):
    CONTROLLER.calls.clear()

    yield CONTROLLER, Path(
        "development/logs/fake_display_timing.log"
    )


def test_parser_accepts_clear_timing():
    args = build_parser().parse_args(
        ["timing", "clear"]
    )

    assert args.lab_command == "timing"
    assert args.timing_operation == "clear"
    assert args.handler is run_display_timing
    assert args.count == 25


def test_parser_accepts_row_timing():
    args = build_parser().parse_args(
        [
            "timing",
            "row",
            "--row",
            "1",
            "--text",
            "HELLO",
        ]
    )

    assert args.row == 1
    assert args.text == "HELLO"


def test_parser_accepts_frame_timing():
    args = build_parser().parse_args(
        [
            "timing",
            "frame",
            "--line1",
            "TOP",
            "--line2",
            "BOTTOM",
        ]
    )

    assert args.line1 == "TOP"
    assert args.line2 == "BOTTOM"


def test_clear_timing_runs_requested_count(monkeypatch):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        ["timing", "clear", "--count", "3", "--interval", "0"]
    )

    result = run_display_timing(args)

    assert result.success is True
    assert result.data["successes"] == 3
    assert CONTROLLER.calls == [
        ("clear",),
        ("clear",),
        ("clear",),
    ]


def test_row_timing_uses_selected_row(monkeypatch):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "timing",
            "row",
            "--row",
            "1",
            "--text",
            "HELLO",
            "--count",
            "2",
            "--interval",
            "0",
        ]
    )

    result = run_display_timing(args)

    assert result.success is True
    assert CONTROLLER.calls == [
        ("write_text", 1, "HELLO"),
        ("write_text", 1, "HELLO"),
    ]


def test_frame_timing_writes_both_lines(monkeypatch):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "timing",
            "frame",
            "--line1",
            "TOP",
            "--line2",
            "BOTTOM",
            "--count",
            "2",
            "--interval",
            "0",
        ]
    )

    result = run_display_timing(args)

    assert result.success is True
    assert CONTROLLER.calls == [
        ("write_frame", "TOP", "BOTTOM"),
        ("write_frame", "TOP", "BOTTOM"),
    ]


def test_main_prints_timing_summary(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(
        [
            "timing",
            "clear",
            "--count",
            "2",
            "--interval",
            "0",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "001: clear" in output
    assert "002: clear" in output
    assert "Command: timing-clear" in output
    assert "2/2 successful" in output


def test_json_mode_suppresses_samples(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(
        [
            "--json",
            "timing",
            "clear",
            "--count",
            "2",
            "--interval",
            "0",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "001: clear" not in output
    assert '"command": "timing-clear"' in output
