import json

import pytest

from truepanel.lab.protocol import (
    CandidateGlyphSerializer,
    CustomGlyph,
    GLYPH_HEIGHT,
    GLYPH_WIDTH,
    GlyphPayloadLayout,
    GlyphUploadPlan,
    VERTICAL_FILL_GLYPHS,
    build_glyph_upload_experiment,
    glyph,
    vertical_fill_level,
)


def test_custom_glyph_requires_eight_rows():
    with pytest.raises(
        ValueError,
        match="exactly eight rows",
    ):
        CustomGlyph.from_rows(
            "short",
            (0, 1),
        )


def test_custom_glyph_rejects_six_bit_row():
    with pytest.raises(
        ValueError,
        match="five bits",
    ):
        CustomGlyph.from_rows(
            "wide",
            (
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0b100000,
            ),
        )


def test_custom_glyph_serializes_rows():
    item = CustomGlyph.from_rows(
        "test",
        range(8),
    )

    assert item.payload == bytes(
        range(8)
    )
    assert item.row_hex[7] == "0x07"


def test_custom_glyph_preview():
    item = CustomGlyph.from_rows(
        "corner",
        (
            0b10000,
            0,
            0,
            0,
            0,
            0,
            0,
            0b00001,
        ),
    )

    assert item.preview() == (
        "#....\n"
        ".....\n"
        ".....\n"
        ".....\n"
        ".....\n"
        ".....\n"
        ".....\n"
        "....#"
    )


def test_vertical_fill_library_has_eight_levels():
    assert len(
        VERTICAL_FILL_GLYPHS
    ) == 8

    assert all(
        len(item.rows) == GLYPH_HEIGHT
        for item in VERTICAL_FILL_GLYPHS
    )


def test_vertical_fill_zero_is_blank():
    item = vertical_fill_level(0)

    assert item.rows == (0,) * 8


def test_vertical_fill_seven_is_full():
    item = vertical_fill_level(7)

    assert item.rows == (31,) * 8


def test_vertical_fill_four_fills_bottom_five_rows():
    item = vertical_fill_level(4)

    assert item.rows == (
        0,
        0,
        0,
        31,
        31,
        31,
        31,
        31,
    )


def test_builtin_glyph_lookup():
    assert glyph("check").name == "check"

    with pytest.raises(
        KeyError,
        match="unknown built-in glyph",
    ):
        glyph("warp-core")


def test_upload_plan_validates_slot():
    with pytest.raises(
        ValueError,
        match="zero and seven",
    ):
        GlyphUploadPlan(
            slot=8,
            glyph=vertical_fill_level(1),
        )


@pytest.mark.parametrize(
    ("layout", "expected"),
    (
        (
            GlyphPayloadLayout.OPCODE_SLOT_ROWS,
            bytes(
                [
                    0x4D,
                    0x10,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x1F,
                    0x1F,
                    0x1F,
                ]
            ),
        ),
        (
            GlyphPayloadLayout.OPCODE_LENGTH_SLOT_ROWS,
            bytes(
                [
                    0x4D,
                    0x10,
                    0x09,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x1F,
                    0x1F,
                    0x1F,
                ]
            ),
        ),
        (
            GlyphPayloadLayout.OPCODE_SLOT_LENGTH_ROWS,
            bytes(
                [
                    0x4D,
                    0x10,
                    0x00,
                    0x08,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x1F,
                    0x1F,
                    0x1F,
                ]
            ),
        ),
    ),
)
def test_candidate_serializers(
    layout,
    expected,
):
    plan = GlyphUploadPlan(
        slot=0,
        glyph=vertical_fill_level(2),
    )

    serializer = CandidateGlyphSerializer(
        opcode=0x10,
        layout=layout,
    )

    assert serializer.serialize(
        plan
    ) == expected


def test_glyph_experiment_contains_restore():
    plan = GlyphUploadPlan(
        slot=0,
        glyph=vertical_fill_level(3),
    )
    serializer = CandidateGlyphSerializer(
        opcode=0x10,
        layout=(
            GlyphPayloadLayout.OPCODE_SLOT_ROWS
        ),
    )

    experiment = (
        build_glyph_upload_experiment(
            plan,
            serializer,
        )
    )

    assert experiment.sequence.has_restore is True
    assert experiment.sequence.steps[-1].payload == (
        b"\x4D\x0D"
    )
    assert experiment.risk.value == (
        "experimental_write"
    )

    json.dumps(
        experiment.as_dict()
    )


def test_foundry_dimensions():
    assert GLYPH_WIDTH == 5
    assert GLYPH_HEIGHT == 8
