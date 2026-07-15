import pytest

from truepanel.lab.display_patterns import (
    DISPLAY_WIDTH,
    DisplayPattern,
    pattern,
    patterns,
)


def test_builtin_patterns_exist():
    names = [item.name for item in patterns()]

    assert names == [
        "alphabet",
        "numbers",
        "checker",
        "solid",
    ]


def test_every_pattern_has_correct_width():
    for item in patterns():
        assert len(item.line1) == DISPLAY_WIDTH
        assert len(item.line2) == DISPLAY_WIDTH


def test_lookup_returns_pattern():
    item = pattern("alphabet")

    assert item.name == "alphabet"
    assert item.line1 == "ABCDEFGHIJKLMNOP"
    assert item.line2 == "QRSTUVWXYZ012345"


def test_unknown_pattern_raises():
    with pytest.raises(KeyError):
        pattern("does-not-exist")


def test_pattern_width_validation_line1():
    with pytest.raises(ValueError):
        DisplayPattern(
            "bad",
            "short",
            "1234567890ABCDEF",
        )


def test_pattern_width_validation_line2():
    with pytest.raises(ValueError):
        DisplayPattern(
            "bad",
            "1234567890ABCDEF",
            "short",
        )


def test_patterns_are_unique():
    names = [item.name for item in patterns()]

    assert len(names) == len(set(names))


def test_patterns_returns_tuple():
    assert isinstance(patterns(), tuple)


def test_lookup_returns_same_object():
    item = pattern("numbers")

    assert item is patterns()[1]


def test_checker_pattern_contents():
    item = pattern("checker")

    assert item.line1.startswith("A1")
    assert item.line2.endswith("1A")
