from contextlib import contextmanager
from pathlib import Path

import pytest

from truepanel.lab.commands import (
    build_parser,
    run_display_timing,
)


class FakeController:
    def __init__(self):
        self.calls = []

    def write_text(self, row, text):
        self.calls.append(
            ("write_text", row, text)
        )


CONTROLLER = FakeController()


@contextmanager
def fake_open_controller(*args, **kwargs):
    CONTROLLER.calls.clear()

    yield CONTROLLER, Path(
        "development/logs/fake_payload_scaling.log"
    )


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (0, ""),
        (1, "A"),
        (2, "AB"),
        (4, "ABCD"),
        (8, "ABCDEFGH"),
        (12, "ABCDEFGHIJKL"),
        (16, "ABCDEFGHIJKLMNOP"),
    ],
)
def test_row_length_generates_canonical_payload(
    monkeypatch,
    length,
    expected,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "timing",
            "row",
            "--length",
            str(length),
            "--count",
            "1",
            "--interval",
            "0",
        ]
    )

    result = run_display_timing(args)

    assert result.success is True
    assert CONTROLLER.calls == [
        ("write_text", 0, expected),
    ]


def test_length_overrides_text(monkeypatch):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "timing",
            "row",
            "--text",
            "SHOULD-NOT-BE-USED",
            "--length",
            "4",
            "--count",
            "1",
            "--interval",
            "0",
        ]
    )

    run_display_timing(args)

    assert CONTROLLER.calls == [
        ("write_text", 0, "ABCD"),
    ]


@pytest.mark.parametrize("length", [-1, 17])
def test_invalid_length_is_rejected(
    monkeypatch,
    length,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "timing",
            "row",
            "--length",
            str(length),
            "--count",
            "1",
        ]
    )

    with pytest.raises(
        ValueError,
        match="between 0 and 16",
    ):
        run_display_timing(args)


def test_text_still_works_without_length(monkeypatch):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )

    args = build_parser().parse_args(
        [
            "timing",
            "row",
            "--text",
            "HELLO",
            "--count",
            "1",
            "--interval",
            "0",
        ]
    )

    run_display_timing(args)

    assert CONTROLLER.calls == [
        ("write_text", 0, "HELLO"),
    ]
