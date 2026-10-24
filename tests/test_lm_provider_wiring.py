"""Verify factory never claims commissioning from well-formed config alone."""
from truepanel.host.factory import build_loadmaster_copy_button_service


class Reader:
    def read_level(self):
        return 1
    def close(self):
        pass


def config():
    return {"mission_control": {"cargo_bay": {"loadmaster": {
        "physical_confirmation": {
            "enabled": True, "source": "fintek_gpio", "bank": 7,
            "bit": 5, "active_low": True,
        }
    }}}}


def test_legacy_factory_without_provider_remains_unarmed():
    service = build_loadmaster_copy_button_service(
        config=config(), reader_factory=Reader,
    )
    assert service is not None
    assert service.preflight_provider is None
    assert not service.snapshot()["armed"]
    service.stop()


def test_legacy_factory_can_accept_injected_provider():
    service = build_loadmaster_copy_button_service(
        config=config(), reader_factory=Reader,
        preflight_provider=lambda: None,
    )
    assert service is not None
    assert callable(service.preflight_provider)
    assert service.preflight_provider() is None
    assert not service.snapshot()["armed"]
    service.stop()
