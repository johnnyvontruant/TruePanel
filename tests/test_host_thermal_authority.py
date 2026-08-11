from truepanel.host.thermal_authority import (
    HostThermalAuthority,
)


class FakeService:
    def request_profile(
        self,
        profile,
        **kwargs,
    ):
        del profile
        del kwargs
        return None


def build_authority(
    *,
    clock=lambda: 100.0,
):
    return HostThermalAuthority(
        service=FakeService(),
        policy_mode="automatic_control",
        command_cooldown_seconds=30.0,
        current_fingerprint="a" * 64,
        commissioned_fingerprint="a" * 64,
        automatic_lease_seconds=86400.0,
        supervised_session_seconds=120.0,
        clock=clock,
    )


def test_authority_always_starts_disarmed():
    authority = build_authority()

    assert authority.operator_armed is False
    assert (
        authority.coordinator.operator_armed
        is False
    )


def test_authority_always_starts_dry_run():
    authority = build_authority()

    assert authority.dry_run is True
    assert authority.coordinator.dry_run is True


def test_authority_owns_fingerprints():
    authority = build_authority()

    assert authority.current_fingerprint == (
        "a" * 64
    )

    assert (
        authority.commissioned_fingerprint
        == "a" * 64
    )


def test_authority_owns_bounded_lease():
    authority = build_authority()

    assert (
        authority.automatic_lease
        .commissioned_fingerprint
        == "a" * 64
    )

    assert authority.automatic_lease.active() is False


def test_supervised_session_is_bounded():
    now = [100.0]

    authority = build_authority(
        clock=lambda: now[0]
    )

    authority.start_supervised_session()

    assert authority.supervised_session_active()
    assert (
        authority.supervised_session_remaining()
        == 120.0
    )

    now[0] = 221.0

    assert not authority.supervised_session_active()
    assert (
        authority.supervised_session_remaining()
        == 0.0
    )


def test_safe_reset_cancels_ephemeral_authority():
    authority = build_authority()

    authority.operator_armed = True
    authority.dry_run = False
    authority.last_result = object()
    authority.supervised_session_deadline = 200.0
    authority.automatic_lease.deadline = 500.0

    authority.coordinator.configure(
        operator_armed=True,
        dry_run=False,
    )

    authority.reset_to_safe_state()

    assert authority.operator_armed is False
    assert authority.dry_run is True
    assert authority.last_result is None

    assert (
        authority.supervised_session_deadline
        is None
    )

    assert (
        authority.automatic_lease.deadline
        is None
    )

    assert (
        authority.coordinator.operator_armed
        is False
    )

    assert authority.coordinator.dry_run is True
    assert authority.coordinator.owns_control is False


def test_configure_authority_updates_coordinator():
    authority = build_authority()

    authority.configure_authority(
        operator_armed=True,
        dry_run=False,
    )

    assert authority.operator_armed is True
    assert authority.dry_run is False

    assert (
        authority.coordinator.operator_armed
        is True
    )

    assert authority.coordinator.dry_run is False
