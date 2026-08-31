from pathlib import Path

from truepanel.activity import ActivityProviderStatus, ZfsActivityProvider
from truepanel.holodeck import DeterministicClock, HoloDeckHostProvider
from truepanel.holodeck.scenario import Scenario

FIXTURES = Path(__file__).parent / "fixtures"
HOST_FIXTURE = FIXTURES / "hosts" / "battlestation" / "host.json"


def build_provider(events):
    scenario = Scenario.from_dict(
        {
            "name": "observatory-zfs-rehearsal",
            "host": "battlestation",
            "events": events,
        }
    )
    return HoloDeckHostProvider.from_path(
        HOST_FIXTURE,
        scenario=scenario,
        clock=DeterministicClock(0),
    )


def zfs_snapshot(provider):
    return ZfsActivityProvider(
        lambda: provider.update().get("zfs_activity", {})
    ).snapshot()


def test_holodeck_replays_zfs_scrub_through_observatory_provider():
    provider = build_provider(
        [
            {
                "at": 5,
                "type": "zfs_activity",
                "scrub_running": True,
                "resilver_running": False,
                "percent": 25,
            },
            {
                "at": 10,
                "type": "zfs_activity",
                "scrub_running": True,
                "resilver_running": False,
                "percent": 60,
            },
            {
                "at": 15,
                "type": "zfs_activity",
                "scrub_running": False,
                "resilver_running": False,
                "percent": 100,
            },
        ]
    )

    idle = zfs_snapshot(provider)
    assert idle.status is ActivityProviderStatus.AVAILABLE
    assert idle.observations == ()

    provider.advance(5)
    quarter = zfs_snapshot(provider)
    assert quarter.status is ActivityProviderStatus.AVAILABLE
    assert len(quarter.observations) == 1
    assert quarter.observations[0].kind == "zfs.scrub"
    assert quarter.observations[0].progress == 0.25

    provider.advance(5)
    progressing = zfs_snapshot(provider)
    assert len(progressing.observations) == 1
    assert progressing.observations[0].kind == "zfs.scrub"
    assert progressing.observations[0].progress == 0.60

    provider.advance(5)
    complete = zfs_snapshot(provider)
    assert complete.status is ActivityProviderStatus.AVAILABLE
    assert complete.observations == ()
    assert [event.type for event in provider.applied_events] == [
        "zfs_activity",
        "zfs_activity",
        "zfs_activity",
    ]


def test_holodeck_zfs_activity_evidence_fails_closed_and_is_bounded():
    provider = build_provider(
        [
            {
                "at": 1,
                "type": "zfs_activity",
                "scrub_running": "yes",
                "resilver_running": False,
                "percent": "not-a-number",
                "raw_status": "must not cross the simulation boundary",
            }
        ]
    )

    state = provider.advance(1)
    assert state["zfs_activity"] == {
        "scrub_running": "yes",
        "resilver_running": False,
        "percent": "not-a-number",
    }

    snapshot = zfs_snapshot(provider)
    assert snapshot.status is ActivityProviderStatus.AVAILABLE
    assert snapshot.observations == ()
