from pathlib import Path

from truepanel.hardware.enclosure import (
    EnclosureController,
    EnclosureSlot,
)


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def create_populated_slot(
    enclosure: Path,
    number: int,
    device: str,
    *,
    status: str = "OK",
    model: str = "ST8000NE001-2M71",
    serial: str = "WKD3TEST",
    wwid: str = "naa.5000c500test",
    locate: str = "0",
    fault: str = "0",
    active: str = "0",
) -> Path:
    slot = enclosure / f"Slot {number:02d}"

    write(slot / "status", status)
    write(slot / "slot", str(number))
    write(slot / "locate", locate)
    write(slot / "fault", fault)
    write(slot / "active", active)

    write(slot / "device" / "model", model)

    serial_bytes = serial.encode("ascii")
    vpd_page = bytes([
        0x00,
        0x80,
        (len(serial_bytes) >> 8) & 0xFF,
        len(serial_bytes) & 0xFF,
    ]) + serial_bytes

    vpd_path = slot / "device" / "vpd_pg80"
    vpd_path.parent.mkdir(parents=True, exist_ok=True)
    vpd_path.write_bytes(vpd_page)

    write(slot / "device" / "wwid", wwid)

    (slot / "device" / "block" / device).mkdir(parents=True)

    return slot


def create_empty_slot(enclosure: Path, number: int) -> Path:
    slot = enclosure / f"Slot {number:02d}"

    write(slot / "status", "not installed")
    write(slot / "slot", str(number))
    write(slot / "locate", "0")
    write(slot / "fault", "0")
    write(slot / "active", "0")

    return slot


def test_missing_root_is_unavailable(tmp_path):
    controller = EnclosureController(tmp_path / "missing")

    assert controller.available() is False
    assert controller.enclosures() == []
    assert controller.slots() == []


def test_discovers_enclosure(tmp_path):
    enclosure = tmp_path / "6:0:0:0"
    enclosure.mkdir()

    controller = EnclosureController(tmp_path)

    assert controller.available() is True
    assert controller.enclosures() == [enclosure]


def test_reads_populated_slot(tmp_path):
    enclosure = tmp_path / "6:0:0:0"
    enclosure.mkdir()

    slot_path = create_populated_slot(
        enclosure,
        2,
        "sdc",
        serial="WKD3MW6D",
        locate="1",
        active="1",
    )

    controller = EnclosureController(tmp_path)
    slots = controller.slots()

    assert len(slots) == 1

    slot = slots[0]

    assert isinstance(slot, EnclosureSlot)
    assert slot.number == 2
    assert slot.installed is True
    assert slot.status == "OK"
    assert slot.model == "ST8000NE001-2M71"
    assert slot.serial == "WKD3MW6D"
    assert slot.wwid == "naa.5000c500test"
    assert slot.device == "sdc"
    assert slot.device_path == "/dev/sdc"
    assert slot.locate is True
    assert slot.fault is False
    assert slot.active is True
    assert slot.enclosure == "6:0:0:0"
    assert slot.sysfs_path == slot_path
    assert slot.display_name == "Bay 2"


def test_reads_empty_slot(tmp_path):
    enclosure = tmp_path / "6:0:0:0"
    enclosure.mkdir()

    create_empty_slot(enclosure, 5)

    controller = EnclosureController(tmp_path)
    slot = controller.slots()[0]

    assert slot.number == 5
    assert slot.installed is False
    assert slot.status == "not installed"
    assert slot.device == ""
    assert slot.device_path == ""
    assert slot.model == ""
    assert slot.serial == ""
    assert slot.wwid == ""


def test_slots_are_sorted_numerically(tmp_path):
    enclosure = tmp_path / "6:0:0:0"
    enclosure.mkdir()

    create_empty_slot(enclosure, 5)
    create_populated_slot(enclosure, 2, "sdc")
    create_populated_slot(enclosure, 0, "sda")

    controller = EnclosureController(tmp_path)

    assert [slot.number for slot in controller.slots()] == [0, 2, 5]


def test_populated_and_empty_filters(tmp_path):
    enclosure = tmp_path / "6:0:0:0"
    enclosure.mkdir()

    create_populated_slot(enclosure, 0, "sda")
    create_populated_slot(enclosure, 1, "sdb")
    create_empty_slot(enclosure, 4)

    controller = EnclosureController(tmp_path)

    assert [slot.number for slot in controller.populated_slots()] == [0, 1]
    assert [slot.number for slot in controller.empty_slots()] == [4]


def test_get_slot(tmp_path):
    enclosure = tmp_path / "6:0:0:0"
    enclosure.mkdir()

    create_populated_slot(enclosure, 3, "sdd")

    controller = EnclosureController(tmp_path)

    assert controller.get_slot(3) is not None
    assert controller.get_slot(3).device == "sdd"
    assert controller.get_slot(99) is None


def test_find_device_accepts_name_or_dev_path(tmp_path):
    enclosure = tmp_path / "6:0:0:0"
    enclosure.mkdir()

    create_populated_slot(enclosure, 1, "sdb")

    controller = EnclosureController(tmp_path)

    assert controller.find_device("sdb").number == 1
    assert controller.find_device("/dev/sdb").number == 1
    assert controller.find_device("/dev/sdz") is None


def test_multiple_enclosures_can_be_disambiguated(tmp_path):
    first = tmp_path / "6:0:0:0"
    second = tmp_path / "7:0:0:0"

    first.mkdir()
    second.mkdir()

    create_populated_slot(first, 0, "sda")
    create_populated_slot(second, 0, "sdb")

    controller = EnclosureController(tmp_path)

    assert controller.get_slot(0, enclosure="6:0:0:0").device == "sda"
    assert controller.get_slot(0, enclosure="7:0:0:0").device == "sdb"
