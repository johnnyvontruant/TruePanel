#!/usr/bin/env python3

from truepanel.display.graphics import progress_frame
from truepanel.display.rom_profiles import ROMGlyphProfile
from truepanel.lab.capture import open_controller


# Levels 0–6 remain blank; level 7 uses the confirmed full block.
ROM_LEVELS = (
    0x20,
    0x20,
    0x20,
    0x20,
    0x20,
    0x20,
    0x20,
    0xFF,
)


def main():
    glyphs = ROMGlyphProfile.from_values(
        ROM_LEVELS,
        name="a125-binary-block",
    ).manager()

    with open_controller(
        "rom-progress-preview",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        for percent in (0, 25, 50, 75, 100):
            frame = progress_frame(
                f"ROM BAR {percent:>3}%",
                percent,
                glyphs,
                width=16,
            )

            controller.write_frame(
                frame.lines[0],
                frame.lines[1],
            )

            response = input(
                f"Viewing {percent}%. "
                "Press Enter for next, or q to quit: "
            ).strip().lower()

            if response == "q":
                break

    print("Capture:", capture)


if __name__ == "__main__":
    main()
