"""
TruePanel hardware-ready graphical widgets.
"""

from __future__ import annotations

from .frame import GraphicsFrame, RawLCDFrame


def graph_frame(title, values, glyphs, width=16):
    return GraphicsFrame(
        title=title[:16],
        payload=glyphs.vertical_bar_graph(
            values,
            width=width,
        ),
    )


def progress_frame(title, percent, glyphs, width=16):
    return GraphicsFrame(
        title=title[:16],
        payload=glyphs.horizontal_bar(
            percent,
            width=width,
        ),
    )


def thermometer_frame(
    label,
    temperature,
    glyphs,
    minimum=20,
    maximum=70,
):
    title = f"{label[:7]} {float(temperature):.0f}C"

    payload = glyphs.thermometer(
        temperature,
        minimum=minimum,
        maximum=maximum,
        width=16,
    )

    return GraphicsFrame(
        title=title,
        payload=payload,
    )


def icon_status_frame(
    title,
    message,
    icon,
    glyphs,
):
    line1 = bytes(
        [glyphs.icon(icon), ord(" ")]
    ) + title.encode("latin-1", errors="replace")

    return RawLCDFrame(
        line1=line1,
        line2=message,
    )
