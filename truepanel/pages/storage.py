from truepanel.menu.page import Page


class PoolHealthPage(Page):
    title = "Pool Health"

    def render(self, state=None):
        pools = (state or {}).get("pools", [])

        if not pools:
            return ["Pool Health", "No Pool Data"]

        bad = [p for p in pools if p.get("health") != "ONLINE"]

        if bad:
            pool = bad[0]
            return ["Pool Alert", f'{pool["name"][:8]} {pool["health"][:7]}']

        return ["Pool Health", "All Healthy"]


class DriveTempPage(Page):
    title = "Drive Temps"

    def __init__(self):
        self.index = 0

    def render(self, state=None):
        temps = (state or {}).get("temps", [])

        if not temps:
            return ["Drive Temps", "No SMART Data"]

        drive_info = temps[self.index % len(temps)]
        self.index += 1

        drive = drive_info.get("drive", "disk")
        temp = drive_info.get("temp", 0)

        if temp >= 50:
            return ["HOT DRIVE", f'{drive[:10]} {temp} C']

        return [f'Drive {drive[:10]}', f'Temp {temp} C']
