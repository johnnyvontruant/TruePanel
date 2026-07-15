from contextlib import contextmanager
from pathlib import Path

from truepanel.lab.commands import (
    build_parser,
    main,
    run_glyph_page,
)


class FakeController:
    def __init__(self):
        self.frames = []

    def write_frame(
        self,
        line1,
        line2,
    ):
        self.frames.append(
            (bytes(line1), bytes(line2))
        )


CONTROLLER = FakeController()


@contextmanager
def fake_open_controller(*args, **kwargs):
    CONTROLLER.frames.clear()

    yield CONTROLLER, Path(
        "development/logs/fake_glyph.log"
    )


def test_parser():
    args = build_parser().parse_args(
        [
            "glyphs",
            "page",
            "3",
        ]
    )

    assert args.lab_command == "glyphs"
    assert args.page == 3
    assert args.handler is run_glyph_page


def test_runner(monkeypatch):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "glyphs",
            "page",
            "2",
        ]
    )

    result = run_glyph_page(args)

    assert result.success
    assert len(CONTROLLER.frames) == 1

    line1, line2 = CONTROLLER.frames[0]

    assert line1[0] == 0x40
    assert line2[-1] == 0x5F


def test_main(monkeypatch, capsys):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    exit_code = main(
        [
            "glyphs",
            "page",
            "1",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0

    assert "Glyph Page 1" in output
    assert "0x20-0x3F" in output
