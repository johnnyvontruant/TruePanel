from truepanel.lab.glyph_runner import (
    GlyphAtlasRunner,
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


def test_display_single_page():
    controller = FakeController()

    runner = GlyphAtlasRunner(controller)

    result = runner.display_page(0)

    assert result.success

    assert len(controller.frames) == 1

    first, second = controller.frames[0]

    assert first == bytes(range(0x00, 0x10))
    assert second == bytes(range(0x10, 0x20))


def test_display_last_page():
    controller = FakeController()

    runner = GlyphAtlasRunner(controller)

    runner.display_page(7)

    first, second = controller.frames[0]

    assert first[0] == 0xE0
    assert second[-1] == 0xFF


def test_display_all():
    controller = FakeController()

    runner = GlyphAtlasRunner(controller)

    callback_pages = []

    runner.display_all(
        delay=0,
        callback=lambda r: callback_pages.append(
            r.page.index
        ),
    )

    assert len(controller.frames) == 8

    assert callback_pages == [
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
    ]
