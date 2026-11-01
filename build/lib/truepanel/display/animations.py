"""
Frame generators for small TruePanel LCD animations.
"""

from truepanel.display.canvas import Canvas
from truepanel.display.widgets import progress_bar, spinner


def startup_frames(title="TruePanel", subtitle="Flight Deck", width=16):
    """Generate a restrained startup sweep."""

    title = str(title)[:width]
    subtitle = str(subtitle)[:width]

    for step in range(width + 1):
        canvas = Canvas(width=width)
        canvas.text(0, 0, title, width=width, align="center")
        canvas.text(0, 1, progress_bar(step * 100 / width, width=width))
        yield canvas.lines

    canvas = Canvas(width=width)
    canvas.text(0, 0, title, width=width, align="center")
    canvas.text(0, 1, subtitle, width=width, align="center")
    yield canvas.lines


def loading_frame(label="Working", frame=0, width=16):
    canvas = Canvas(width=width)
    canvas.text(0, 0, label, width=width)
    canvas.text(0, 1, f"{spinner(frame)} Please wait", width=width)
    return canvas.lines
