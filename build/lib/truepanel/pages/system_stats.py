from truepanel.menu.page import Page


class CpuRamPage(Page):
    title = "CPU/RAM"

    def render(self, state=None):
        if state is None:
            return ["CPU: ?", "RAM: ?"]

        return [
            f'CPU: {state.get("cpu_percent", 0)}%',
            f'RAM: {state.get("ram_percent", 0)}%',
        ]
