from truepanel.host.thermal_lifecycle import (
    HostThermalLifecycleCoordinator,
)


class FakeAuthority:
    def __init__(self):
        self.supervised_calls = []
        self.lease_calls = []
        self.active = True

    def end_supervised_session(self, reason, **kwargs):
        self.supervised_calls.append((reason, kwargs))
        return "supervised-ended"

    def supervised_session_active(self):
        return self.active

    def end_automatic_lease(self, reason, **kwargs):
        self.lease_calls.append((reason, kwargs))
        return "lease-ended"


class FakeSafety:
    def __init__(self):
        self.restore_calls = []
        self.status_calls = []

    def telemetry(self):
        return {"telemetry_fresh": True}

    def restore_automatic(self, reason, **kwargs):
        self.restore_calls.append((reason, kwargs))
        return "restored"

    def publish_status(self, reason=None):
        self.status_calls.append(reason)
        return {"reason": reason}


def build_lifecycle():
    authority = FakeAuthority()
    safety = FakeSafety()
    commissioning = []

    coordinator = HostThermalLifecycleCoordinator(
        thermal_authority=authority,
        safety=safety,
        record_commissioning_event=(
            lambda *args, **kwargs: commissioning.append(
                (args, kwargs)
            )
        ),
    )

    return coordinator, authority, safety, commissioning


def test_supervised_session_uses_host_callbacks():
    coordinator, authority, safety, commissioning = build_lifecycle()

    result = coordinator.end_supervised_session(
        "session complete",
        lifecycle_action="supervised_session_ended",
        telemetry={"sample": 1},
    )

    assert result == "supervised-ended"
    reason, kwargs = authority.supervised_calls[0]
    assert reason == "session complete"
    assert kwargs["telemetry"] == {"sample": 1}
    assert kwargs["telemetry_provider"]() == {"telemetry_fresh": True}
    assert kwargs["restore_automatic"]("restore") == "restored"
    assert kwargs["publish_status"](reason="publish") == {"reason": "publish"}
    kwargs["record_commissioning_event"]("event", "reason")
    assert safety.restore_calls[0][0] == "restore"
    assert safety.status_calls == ["publish"]
    assert commissioning[0][0] == ("event", "reason")


def test_bounded_lease_uses_host_callbacks_and_restore_flag():
    coordinator, authority, safety, commissioning = build_lifecycle()

    result = coordinator.end_bounded_automatic_lease(
        "lease complete",
        lifecycle_action="automatic_lease_cancelled",
        telemetry={"sample": 2},
        restore=False,
    )

    assert result == "lease-ended"
    reason, kwargs = authority.lease_calls[0]
    assert reason == "lease complete"
    assert kwargs["telemetry"] == {"sample": 2}
    assert kwargs["restore"] is False
    assert kwargs["telemetry_provider"]() == {"telemetry_fresh": True}
    assert kwargs["restore_automatic"]("restore") == "restored"
    assert kwargs["publish_status"](reason="publish") == {"reason": "publish"}
    kwargs["record_commissioning_event"]("event", "reason")
    assert safety.restore_calls[0][0] == "restore"
    assert safety.status_calls == ["publish"]
    assert commissioning[0][0] == ("event", "reason")


def test_supervised_session_activity_is_authority_owned():
    coordinator, authority, _, _ = build_lifecycle()

    assert coordinator.supervised_session_active() is True

    authority.active = False

    assert coordinator.supervised_session_active() is False
