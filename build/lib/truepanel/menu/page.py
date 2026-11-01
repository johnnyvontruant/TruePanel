class Page:
    """
    Base LCD page.

    A page returns two strings, each 16 characters or less.
    """

    title = "Page"

    def render(self, state=None):
        return [self.title[:16], ""]

    def on_select(self, state=None):
        return None
