from contextlib import contextmanager
from pathlib import Path

import pytest

from truepanel.lab.commands import (
    build_parser,
    main,
    run_display_characterize,
)


class FakeController:
    def __init__(self):
        self.calls = []

    def clear(self):
        self.calls.append(("clear",))

    def write_frame(self, line1, line2):
        self.calls.append(
            ("write", line1, line2)
        )


CONTROLLER = FakeController()


@contextmanager
def fake_open_controller(*args, **kwargs):
    CONTROLLER.calls.clear()

    yield CONTROLLER, Path(
        "development/logs/fake_display.log"
    )


def test_parser_accepts_display_characterize():
    args = build_parser().parse_args(
        ["display", "characterize"]
    )

    assert args.lab_command == "display"
    assert args.display_command == "characterize"
    assert args.handler is run_display_characterize
    assert args.duration == pytest.approx(1.0)


def test_parser_accepts_custom_duration():
    args = build_parser().parse_args(
        [
            "display",
            "characterize",
            "--duration",
            "0.25",
        ]
    )

    assert args.duration == pytest.approx(0.25)


def test_characterization_executes_all_frames(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )
    monkeypatch.setattr(
        "truepanel.lab.display_runner.time.sleep",
        lambda _: None,
    )

    args = build_parser().parse_args(
        [
            "display",
            "characterize",
            "--duration",
            "0",
        ]
    )

    result = run_display_characterize(args)

    writes = [
        call
        for call in CONTROLLER.calls
        if call[0] == "write"
    ]

    assert result.success is True
    assert result.command == "display-characterize"
    assert result.data["frame_count"] == 4
    assert len(writes) == 4


def test_characterization_clears_before_and_after(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "display",
            "characterize",
            "--duration",
            "0",
        ]
    )

    run_display_characterize(args)

    assert CONTROLLER.calls[0] == ("clear",)
    assert CONTROLLER.calls[-1] == ("clear",)


def test_characterization_uses_canonical_patterns(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "display",
            "characterize",
            "--duration",
            "0",
        ]
    )

    run_display_characterize(args)

    writes = [
        call
        for call in CONTROLLER.calls
        if call[0] == "write"
    ]

    assert writes[0][1:] == (
        "ABCDEFGHIJKLMNOP",
        "QRSTUVWXYZ012345",
    )
    assert writes[-1][1:] == (
        "################",
        "................",
    )


def test_negative_duration_is_rejected():
    args = build_parser().parse_args(
        [
            "display",
            "characterize",
            "--duration",
            "-1",
        ]
    )

    with pytest.raises(
        ValueError,
        match="non-negative",
    ):
        run_display_characterize(args)


def test_main_prints_frame_progress(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(
        [
            "display",
            "characterize",
            "--duration",
            "0",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Frame 1/4" in output
    assert "Frame 4/4" in output
    assert "ABCDEFGHIJKLMNOP" in output
    assert "4 frames completed" in output


def test_json_mode_suppresses_frame_progress(
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
            "display",
            "characterize",
            "--duration",
            "0",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Frame 1/4" not in output
    assert '"command": "display-characterize"' in output
