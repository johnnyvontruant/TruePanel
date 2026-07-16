#!/usr/bin/env python3

from truepanel.lab.capture import open_controller


CANDIDATES = [
    0x20,
    0xA1,
    0xA5,
    0xFF,
]


def main():
    with open_controller(
        "rom-fill-comparison",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        for value in CANDIDATES:
            controller.write_frame(
                f"ROM 0x{value:02X}",
                bytes([value] * 16),
            )

            response = input(
                f"Viewing 0x{value:02X}. "
                "Press Enter for next, or q to quit: "
            ).strip().lower()

            if response == "q":
                break

    print("Capture:", capture)


if __name__ == "__main__":
    main()
