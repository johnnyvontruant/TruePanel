from types import SimpleNamespace

from truepanel.web import bay_mirror
from truepanel.web.bay_mirror import BayMirrorProvider


STATUS = """
  pool: HDDs
 state: ONLINE
config:

        NAME          STATE     READ WRITE CKSUM
        HDDs          ONLINE       0     0     0
          raidz1-0    ONLINE       0     0     0
            /dev/sda1 ONLINE       0     0     0
            /dev/sdb1 ONLINE       0     0     0
            /dev/sdc1 ONLINE       0     0     0
            /dev/sdd1 ONLINE       0     0     0
            /dev/sde1 ONLINE       0     0     0
            /dev/sdf1 ONLINE       0     0     0

errors: No known data errors
"""


def bay(number, device, *, installed=True, source="kernel", locate=False, fault=False):
    return SimpleNamespace(
        physical_bay=number,
        installed=installed,
        mapping_source=source,
        device=device,
        kernel_slot_state=SimpleNamespace(
            locate=locate,
            fault=fault,
        ),
    )


class Inventory:
    def __init__(self, bays):
        self._bays = list(bays)

    def front_bays(self):
        return list(self._bays)


def test_bay_mirror_correlates_all_six_bays_without_identity_leakage():
    provider = BayMirrorProvider(
        inventory=Inventory(
            [
                bay(1, "sda"),
                bay(2, "sdb"),
                bay(3, "sdc"),
                bay(4, "sdd"),
                bay(5, "sde", source="configured"),
                bay(6, "sdf", source="configured"),
            ]
        ),
        status_runner=lambda: STATUS,
    )

    payload = provider.snapshot()

    assert payload["schema_version"] == 1
    assert payload["read_only_hardware"] is True
    assert payload["privacy_safe"] is True
    assert payload["available"] is True
    assert payload["count"] == 6

    assert [item["bay"] for item in payload["bays"]] == [1, 2, 3, 4, 5, 6]
    assert {item["state"] for item in payload["bays"]} == {"online"}
    assert {item["pool"] for item in payload["bays"]} == {"HDDs"}
    assert payload["bays"][4]["mapping_source"] == "configured"

    forbidden = {
        "device",
        "device_path",
        "serial",
        "serial_last4",
        "wwn",
        "wwid",
        "model",
        "partuuid",
        "capacity_bytes",
    }
    for item in payload["bays"]:
        assert forbidden.isdisjoint(item)


def test_bay_mirror_fails_closed_for_unknown_and_missing_bays():
    provider = BayMirrorProvider(
        inventory=Inventory(
            [
                bay(1, "sda"),
                bay(2, "", installed=False),
                bay(5, "", installed=False, source="configured-missing"),
            ]
        ),
        status_runner=lambda: "",
    )

    payload = provider.snapshot()

    assert payload["bays"][0]["state"] == "unknown"
    assert payload["bays"][1]["state"] == "empty"
    assert payload["bays"][2]["state"] == "missing"


def test_bay_mirror_surfaces_locate_and_fault_without_hardware_writes():
    provider = BayMirrorProvider(
        inventory=Inventory(
            [
                bay(1, "sda", locate=True),
                bay(2, "sdb", fault=True),
            ]
        ),
        status_runner=lambda: STATUS,
    )

    payload = provider.snapshot()

    assert payload["bays"][0]["state"] == "identify"
    assert payload["bays"][1]["state"] == "fault"


def test_bay_mirror_marks_present_nonmember_as_attention_not_online():
    provider = BayMirrorProvider(
        inventory=Inventory([bay(1, "sdz")]),
        status_runner=lambda: STATUS,
    )

    payload = provider.snapshot()

    assert payload["bays"][0]["state"] == "present"
    assert payload["bays"][0]["pool"] is None
    assert payload["bays"][0]["zfs_state"] is None


def test_bay_mirror_honors_mission_control_config_environment(monkeypatch, tmp_path):
    config_path = tmp_path / "installed-truepanel.yaml"
    config_path.write_text("hardware: {}\n", encoding="utf-8")
    monkeypatch.setenv("TRUEPANEL_MC_CONFIG_PATH", str(config_path))

    provider = BayMirrorProvider(
        inventory=Inventory([]),
        status_runner=lambda: "",
    )

    assert provider._config_path == config_path.resolve()


def test_bay_mirror_defaults_to_installed_truepanel_config(monkeypatch, tmp_path):
    monkeypatch.delenv("TRUEPANEL_MC_CONFIG_PATH", raising=False)
    monkeypatch.setattr(bay_mirror, "installation_root", lambda: tmp_path)

    provider = BayMirrorProvider(
        inventory=Inventory([]),
        status_runner=lambda: "",
    )

    assert provider._config_path == tmp_path / "truepanel.yaml"


def test_device_bay_map_returns_internal_device_to_bay_mapping():
    provider = BayMirrorProvider(
        inventory=Inventory(
            [
                bay(1, "sda"),
                bay(2, "sdb"),
                bay(3, "sdc"),
            ]
        ),
        status_runner=lambda: STATUS,
    )

    mapping = provider.device_bay_map()

    assert mapping == {"sda": 1, "sdb": 2, "sdc": 3}


def test_device_bay_map_excludes_empty_bays_and_missing_devices():
    provider = BayMirrorProvider(
        inventory=Inventory(
            [
                bay(1, "sda"),
                bay(2, "", installed=False),
                bay(0, "sdz"),
            ]
        ),
        status_runner=lambda: STATUS,
    )

    mapping = provider.device_bay_map()

    assert mapping == {"sda": 1}


def test_device_bay_map_never_raises_on_inventory_failure():
    class BrokenInventory:
        def front_bays(self):
            raise RuntimeError("enclosure unavailable")

    provider = BayMirrorProvider(
        inventory=BrokenInventory(),
        status_runner=lambda: STATUS,
    )

    assert provider.device_bay_map() == {}


def test_device_bay_map_is_not_privacy_scrubbed_unlike_snapshot():
    """device_bay_map is explicitly for internal joins only, never sent to a
    client directly; snapshot() remains the privacy-safe public contract."""
    provider = BayMirrorProvider(
        inventory=Inventory([bay(1, "sda")]),
        status_runner=lambda: STATUS,
    )

    assert provider.device_bay_map() == {"sda": 1}
    assert "device" not in provider.snapshot()["bays"][0]
