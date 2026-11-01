"""
Small character-cell canvas for the TruePanel 16x2 LCD.
"""

from truepanel.display.charset import LCD_HEIGHT, LCD_WIDTH, sanitize


class Canvas:
    """A fixed-size character canvas suitable for the QNAP LCD."""

    def __init__(self, width=LCD_WIDTH, height=LCD_HEIGHT, fill=" "):
        if width <= 0 or height <= 0:
            raise ValueError("Canvas dimensions must be positive")

        self.width = int(width)
        self.height = int(height)
        self.fill = sanitize(fill or " ")[0]
        self.clear()

    def clear(self, fill=None):
        if fill is not None:
            self.fill = sanitize(fill or " ")[0]

        self._cells = [
            [self.fill for _ in range(self.width)]
            for _ in range(self.height)
        ]
        return self

    def text(self, x, y, value, width=None, align="left"):
        if not 0 <= y < self.height:
            return self

        value = sanitize(value)

        if width is not None:
            width = max(0, int(width))
            value = value[:width]

            if align == "right":
                value = value.rjust(width)
            elif align == "center":
                value = value.center(width)
            else:
                value = value.ljust(width)

        for offset, char in enumerate(value):
            column = x + offset

            if 0 <= column < self.width:
                self._cells[y][column] = char

        return self

    def char(self, x, y, value):
        return self.text(x, y, sanitize(value)[:1])

    def hline(self, x, y, width, char="-"):
        return self.text(x, y, sanitize(char)[:1] * max(0, int(width)))

    def render(self, pad=True):
        lines = ["".join(row) for row in self._cells]

        if not pad:
            return [line.rstrip() for line in lines]

        return [line[:self.width].ljust(self.width) for line in lines]

    @property
    def lines(self):
        return self.render()
