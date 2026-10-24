"""Automatic arming remains off unless a trusted evidence provider exists."""
from time import monotonic
from truepanel.cargo.copy_button import LoadmasterPhysicalPreflight
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService


class Reader:
    def read_level(self):
        return 1
    def close(self):
        pass


def preflight(**overrides):
    data = dict(
        cartridge_id="Untitled", cartridge_uuid="6ADA-80D5",
        device_serial="2532EA8D421A", plan_state="READY",
        backup_files=1, backup_bytes=64, baseline_verified=True,
        identity_verified=True, backlog_verified=True,
        plan_digest="a" * 64, generated_at_monotonic=monotonic(),
    )
    data.update(overrides)
    return LoadmasterPhysicalPreflight(**data)


def test_no_provider_is_inert():
    service = LoadmasterCopyButtonService(reader=Reader())
    assert service.preflight_provider is None
    assert not service.snapshot()["armed"]


def test_provider_must_supply_complete_verified_preflight():
    invalid = preflight(baseline_verified=False)
    service = LoadmasterCopyButtonService(
        reader=Reader(), preflight_provider=lambda: invalid,
        poll_seconds=0.01,
    )
    service.start()
    import time
    time.sleep(0.05)
    assert not service.snapshot()["armed"]
    service.stop()


def test_verified_preflight_arms_and_revocation_disarms():
    state = {"evidence": preflight()}
    service = LoadmasterCopyButtonService(
        reader=Reader(),
        preflight_provider=lambda: state["evidence"],
        poll_seconds=0.01,
    )
    import time
    service.start()
    time.sleep(0.06)
    assert service.snapshot()["armed"]
    state["evidence"] = None
    time.sleep(0.06)
    assert not service.snapshot()["armed"]
    service.stop()
