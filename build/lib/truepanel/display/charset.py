"""
TruePanel LCD character handling.

The QNAP LCD is treated as an ASCII-first character display. Rich glyphs may
look good in a terminal but are not guaranteed to exist in the LCD character
ROM, so every decorative symbol has a conservative fallback.
"""

LCD_WIDTH = 16
LCD_HEIGHT = 2


GLYPHS = {
    "filled": "#",
    "empty": "-",
    "activity_low": ".",
    "activity_mid": "=",
    "activity_high": "#",
    "healthy": "O",
    "info": "i",
    "warning": "!",
    "critical": "X",
    "up": "^",
    "down": "v",
    "right": ">",
    "left": "<",
    "degree": "C",
    "spinner_0": "|",
    "spinner_1": "/",
    "spinner_2": "-",
    "spinner_3": "\\",
}


TRANSLITERATION = {
    "█": "#",
    "▓": "#",
    "▒": "=",
    "░": "-",
    "●": "O",
    "○": "o",
    "▲": "^",
    "▼": "v",
    "▶": ">",
    "◀": "<",
    "↑": "^",
    "↓": "v",
    "→": ">",
    "←": "<",
    "°": "o",
    "•": "*",
    "·": ".",
    "✓": "Y",
    "✗": "X",
    "–": "-",
    "—": "-",
    "…": "...",
}


def glyph(name, default="?"):
    """Return a named LCD-safe glyph."""

    return GLYPHS.get(name, default)


def sanitize(text, width=None, pad=False):
    """
    Convert text to conservative LCD-safe ASCII.

    Unknown non-ASCII characters become question marks rather than being sent
    directly to the LCD controller.
    """

    if text is None:
        text = ""

    result = []

    for char in str(text):
        replacement = TRANSLITERATION.get(char, char)

        for output_char in replacement:
            code = ord(output_char)
            result.append(output_char if 32 <= code <= 126 else "?")

    rendered = "".join(result)

    if width is not None:
        rendered = rendered[:width]
        if pad:
            rendered = rendered.ljust(width)

    return rendered
