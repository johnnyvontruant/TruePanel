from dataclasses import dataclass


@dataclass
class MissionEvent:
    priority: int
    title: str
    message: str
    category: str = "info"
    timeout: int = 5


class MissionControl:
    def __init__(self):
        self.detectors = []

    def register(self, detector):
        self.detectors.append(detector)

    def evaluate(self, state):
        events = []

        for detector in self.detectors:
            event = detector(state)
            if event:
                events.append(event)

        if not events:
            return MissionEvent(
                priority=0,
                title="TruePanel",
                message="No Status"
            )

        return max(events, key=lambda e: e.priority)


def pool_detector(state):

    pools = state.get("pools", [])

    if not pools:
        return None

    for pool in pools:
        if pool.get("health") != "ONLINE":
            return MissionEvent(
                priority=100,
                title="POOL ALERT",
                message=f'{pool["name"]} {pool["health"]}',
                category="storage",
                timeout=15,
            )

    return None


def healthy_detector(state):

    return MissionEvent(
        priority=10,
        title="BattleStation",
        message="Healthy",
        category="healthy",
    )

if __name__ == "__main__":

    mc = MissionControl()

    mc.register(pool_detector)
    mc.register(healthy_detector)

    event = mc.evaluate({
        "pools": [
            {"name": "tank", "health": "DEGRADED"}
        ]
    })

    print(event)
