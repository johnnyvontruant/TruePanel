import pytest

from truepanel.lab.glyph_atlas import (
    BYTE_MAX,
    BYTE_MIN,
    GLYPHS_PER_PAGE,
    GLYPHS_PER_ROW,
    atlas_page,
    build_atlas,
    build_page,
)


def test_build_first_page():
    page = build_page(0x00)

    assert page.index == 0
    assert page.start == 0x00
    assert page.end == 0x1F
    assert page.label == "0x00-0x1F"


def test_build_last_page():
    page = build_page(0xE0)

    assert page.index == 7
    assert page.start == 0xE0
    assert page.end == BYTE_MAX
    assert page.label == "0xE0-0xFF"


def test_line_lengths():
    page = build_page(0x20)

    assert len(page.line1) == GLYPHS_PER_ROW
    assert len(page.line2) == GLYPHS_PER_ROW


def test_first_page_contents():
    page = build_page(0x00)

    assert page.line1 == bytes(range(0x00, 0x10))
    assert page.line2 == bytes(range(0x10, 0x20))


def test_second_page_contents():
    page = build_page(0x20)

    assert page.line1[0] == 0x20
    assert page.line2[-1] == 0x3F


def test_build_full_atlas():
    atlas = build_atlas()

    assert len(atlas) == 8


def test_page_lookup():
    page = atlas_page(3)

    assert page.start == 0x60
    assert page.end == 0x7F


@pytest.mark.parametrize(
    "index",
    [-1, 8],
)
def test_invalid_page_index(index):
    with pytest.raises(ValueError):
        atlas_page(index)


@pytest.mark.parametrize(
    "start",
    [-1, 0x100],
)
def test_invalid_page_start(start):
    with pytest.raises(ValueError):
        build_page(start)


def test_alignment_required():
    with pytest.raises(ValueError):
        build_page(0x01)


def test_page_dictionary():
    page = build_page(0x40)

    payload = page.as_dict()

    assert payload["start_hex"] == "0x40"
    assert payload["end_hex"] == "0x5F"
    assert payload["label"] == "0x40-0x5F"


def test_partial_atlas():
    atlas = build_atlas(
        start=0x40,
        end=0x9F,
    )

    assert len(atlas) == 3

    assert atlas[0].start == 0x40
    assert atlas[-1].start == 0x80


def test_invalid_range():
    with pytest.raises(ValueError):
        build_atlas(
            start=0x80,
            end=0x40,
        )


def test_constants():
    assert BYTE_MIN == 0x00
    assert BYTE_MAX == 0xFF
    assert GLYPHS_PER_PAGE == 32
