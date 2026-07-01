class MenuEngine:
    def __init__(self):
        self.pages = []
        self.index = 0

    def register(self, page):
        self.pages.append(page)

    def current_page(self):
        if not self.pages:
            return None
        return self.pages[self.index]

    def next(self):
        if self.pages:
            self.index = (self.index + 1) % len(self.pages)

    def previous(self):
        if self.pages:
            self.index = (self.index - 1) % len(self.pages)

    def render(self, state=None):
        page = self.current_page()
        if page is None:
            return ["TruePanel", "No Pages"]

        try:
            lines = page.render(state)
        except Exception as exc:
            lines = ["Page Error", str(exc)[:16]]

        return self._normalize(lines)

    def select(self, state=None):
        page = self.current_page()
        if page is None:
            return None

        try:
            return page.on_select(state)
        except Exception as exc:
            return ["Select Error", str(exc)[:16]]

    def _normalize(self, lines):
        if not isinstance(lines, (list, tuple)):
            lines = [str(lines), ""]

        if len(lines) < 2:
            lines = list(lines) + [""]

        return [
            str(lines[0])[:16],
            str(lines[1])[:16],
        ]
