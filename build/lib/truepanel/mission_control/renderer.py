"""
Mission Control Renderer

Converts MissionEvent objects into LCD-safe text lines.
"""


def fit_lcd(text, width=16):
    text = str(text)
    return text[:width]


def render_event(event):
    return [
        fit_lcd(event.title),
        fit_lcd(event.message),
    ]
