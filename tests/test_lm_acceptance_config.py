"""Synthetic physical commissioning cannot escape its SSD lab."""
import pytest

from truepanel.loadmaster.config import LoadmasterConfigError, load_settings

LAB = "/mnt/SSDs/Applications/Loadmaster-V2-Lab"
FOLDER = "LOADMASTER-V2-ACCEPTANCE-20261023-175315"


def config():
    return {"loadmaster": {
        "enabled": True,
        "physical_bridge_enabled": True,
        "external_daemon": True,
        "physical_acceptance_receipt": LAB + "/physical-commissioning/synthetic-baseline.json",
        "state_dir": LAB + "/isolated-service/state",
        "mount_root": LAB + "/isolated-service/mount",
        "status_path": LAB + "/isolated-service/status.json",
        "command_socket": LAB + "/isolated-service/command.sock",
        "physical_token_key": LAB + "/isolated-service/host.key",
        "remote_start": False,
        "verify": "sha256",
        "drives": [{"name": "Untitled", "nas_path": LAB + "/" + FOLDER,
                    "usb_folder": FOLDER}],
    }}


def test_exact_lab_config():
    settings = load_settings(config())
    assert settings.extra["physical_acceptance_mode"] is True
    assert settings.extra["physical_bridge_enabled"] is True


@pytest.mark.parametrize("field,value", [
    ("state_dir", "/var/lib/truepanel/loadmaster"),
    ("mount_root", "/mnt/loadmaster"),
    ("status_path", "/run/truepanel/loadmaster-status.json"),
    ("command_socket", "/run/truepanel/loadmaster-command.sock"),
    ("physical_token_key", "/tmp/host.key"),
    ("remote_start", True),
    ("verify", "size"),
    ("physical_bridge_enabled", False),
    ("external_daemon", False),
])
def test_escape_or_weaken_rejected(field, value):
    value_config = config()
    value_config["loadmaster"][field] = value
    with pytest.raises(LoadmasterConfigError):
        load_settings(value_config)


def test_real_media_scope_rejected():
    value_config = config()
    value_config["loadmaster"]["drives"][0]["nas_path"] = "/mnt/HDDs/Shows"
    with pytest.raises(LoadmasterConfigError):
        load_settings(value_config)
