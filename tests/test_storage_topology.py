from pathlib import Path

from truepanel.hardware.enclosure import EnclosureController
from truepanel.hardware.inventory import StorageInventory
from truepanel.hardware.topology import TopologyResolver


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_vpd_serial(path: Path, serial: str) -> None:
    serial_bytes = serial.encode("ascii")
    data = bytes([
        0x00,
        0x80,
        (len(serial_bytes) >> 8) & 0xFF,
        len(serial_bytes) & 0xFF,
    ]) + serial_bytes

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def create_slot(
    enclosure: Path,
    number: int,
    *,
    device: str = "",
    serial: str = "",
    model: str = "ST8000NE001-2M71",
) -> None:
    slot = enclosure / f"Slot {number:02d}"

    write(slot / "slot", str(number))
    write(slot / "locate", "0")
    write(slot / "fault", "0")
    write(slot / "active", "0")

    if device:
        write(slot / "status", "OK")
        write(slot / "device" / "model", model)
        write(slot / "device" / "wwid", f"naa.{serial}")
        write_vpd_serial(slot / "device" / "vpd_pg80", serial)
        (slot / "device" / "block" / device).mkdir(parents=True)
    else:
        write(slot / "status", "not installed")


def create_drive(
    block_root: Path,
    device: str,
    *,
    model: str,
    serial: str,
    transport: str,
    removable: str = "0",
    sectors: int = 1000,
) -> None:
    drive = block_root / device

    write(drive / "device" / "model", model)
    write(drive / "device" / "serial", serial)
    write(drive / "device" / "transport", transport)
    write(drive / "removable", removable)
    write(drive / "size", str(sectors))


def build_controller(tmp_path: Path) -> EnclosureController:
    enclosure_root = tmp_path / "enclosure"
    enclosure = enclosure_root / "6:0:0:0"
    enclosure.mkdir(parents=True)

    create_slot(enclosure, 0, device="sdb", serial="SERIAL1")
    create_slot(enclosure, 1, device="sda", serial="SERIAL2")
    create_slot(enclosure, 2, device="sdc", serial="SERIAL3")
    create_slot(enclosure, 3, device="sdd", serial="SERIAL4")
    create_slot(enclosure, 4)
    create_slot(enclosure, 5)

    return EnclosureController(enclosure_root)


def build_block_root(tmp_path: Path) -> Path:
    block_root = tmp_path / "block"
    block_root.mkdir()

    create_drive(
        block_root,
        "sda",
        model="Front Disk",
        serial="SERIAL2",
        transport="sata",
    )
    create_drive(
        block_root,
        "sdb",
        model="Front Disk",
        serial="SERIAL1",
        transport="sata",
    )
    create_drive(
        block_root,
        "sdc",
        model="Front Disk",
        serial="SERIAL3",
        transport="sata",
    )
    create_drive(
        block_root,
        "sdd",
        model="Front Disk",
        serial="SERIAL4",
        transport="sata",
    )
    create_drive(
        block_root,
        "sdf",
        model="Front Disk",
        serial="SERIAL5",
        transport="sata",
    )
    create_drive(
        block_root,
        "sdg",
        model="Front Disk",
        serial="SERIAL6",
        transport="sata",
    )
    create_drive(
        block_root,
        "sde",
        model="USB DISK MODULE",
        serial="BOOT1",
        transport="usb",
        removable="1",
    )
    create_drive(
        block_root,
        "nvme0n1",
        model="Samsung NVMe",
        serial="NVME1",
        transport="nvme",
    )
    create_drive(
        block_root,
        "nvme1n1",
        model="Samsung NVMe",
        serial="NVME2",
        transport="nvme",
    )

    return block_root


def test_kernel_slots_use_human_facing_bay_numbers(tmp_path):
    controller = build_controller(tmp_path)
    resolver = TopologyResolver()

    bays = resolver.resolve_front_bays(controller.slots(), [])

    assert [bay.kernel_slot for bay in bays] == [0, 1, 2, 3, 4, 5]
    assert [bay.physical_bay for bay in bays] == [1, 2, 3, 4, 5, 6]
    assert bays[0].display_name == "Bay 1"
    assert bays[5].display_name == "Bay 6"


def test_serial_overrides_fill_kernel_empty_slots(tmp_path):
    controller = build_controller(tmp_path)
    block_root = build_block_root(tmp_path)

    resolver = TopologyResolver({
        "front_bays": {
            5: {"serial": "SERIAL5"},
            6: {"serial": "SERIAL6"},
        }
    })

    inventory = StorageInventory(
        enclosure=controller,
        topology=resolver,
        block_root=block_root,
    )

    bays = inventory.front_bays()

    assert bays[4].device == "sdf"
    assert bays[4].serial == "SERIAL5"
    assert bays[4].installed is True
    assert bays[4].mapping_source == "configured"

    assert bays[5].device == "sdg"
    assert bays[5].serial == "SERIAL6"
    assert bays[5].installed is True
    assert bays[5].mapping_source == "configured"


def test_serial_mapping_survives_device_name_changes(tmp_path):
    controller = build_controller(tmp_path)
    block_root = build_block_root(tmp_path)

    original = block_root / "sdf"
    renamed = block_root / "sdz"
    original.rename(renamed)

    resolver = TopologyResolver({
        "front_bays": {
            5: {"serial": "SERIAL5"},
        }
    })

    inventory = StorageInventory(
        enclosure=controller,
        topology=resolver,
        block_root=block_root,
    )

    bay5 = inventory.front_bays()[4]

    assert bay5.device == "sdz"
    assert bay5.serial == "SERIAL5"
    assert bay5.mapping_source == "configured"


def test_missing_configured_drive_is_reported(tmp_path):
    controller = build_controller(tmp_path)
    block_root = build_block_root(tmp_path)

    resolver = TopologyResolver({
        "front_bays": {
            5: {"serial": "NOT-PRESENT"},
        }
    })

    inventory = StorageInventory(
        enclosure=controller,
        topology=resolver,
        block_root=block_root,
    )

    bay5 = inventory.front_bays()[4]

    assert bay5.installed is False
    assert bay5.device == ""
    assert bay5.mapping_source == "configured-missing"


def test_inventory_classifies_complete_machine(tmp_path):
    controller = build_controller(tmp_path)
    block_root = build_block_root(tmp_path)

    resolver = TopologyResolver({
        "front_bays": {
            5: {"serial": "SERIAL5"},
            6: {"serial": "SERIAL6"},
        }
    })

    inventory = StorageInventory(
        enclosure=controller,
        topology=resolver,
        block_root=block_root,
    )

    entries = inventory.devices()

    assert len(inventory.by_category("front-bay")) == 6
    assert len(inventory.by_category("internal-nvme")) == 2
    assert len(inventory.by_category("boot-media")) == 1
    assert len(inventory.by_category("unassigned")) == 0

    assert [entry.label for entry in entries[:6]] == [
        "Bay 1",
        "Bay 2",
        "Bay 3",
        "Bay 4",
        "Bay 5",
        "Bay 6",
    ]


def test_unmapped_sata_disk_is_unassigned(tmp_path):
    controller = build_controller(tmp_path)
    block_root = build_block_root(tmp_path)

    resolver = TopologyResolver()

    inventory = StorageInventory(
        enclosure=controller,
        topology=resolver,
        block_root=block_root,
    )

    unassigned = inventory.by_category("unassigned")

    assert {entry.device for entry in unassigned} == {"sdf", "sdg"}


def test_find_device_accepts_dev_path(tmp_path):
    controller = build_controller(tmp_path)
    block_root = build_block_root(tmp_path)

    resolver = TopologyResolver({
        "front_bays": {
            5: {"serial": "SERIAL5"},
            6: {"serial": "SERIAL6"},
        }
    })

    inventory = StorageInventory(
        enclosure=controller,
        topology=resolver,
        block_root=block_root,
    )

    entry = inventory.find_device("/dev/sdf")

    assert entry is not None
    assert entry.category == "front-bay"
    assert entry.physical_bay == 5


def test_partitions_and_loop_devices_are_ignored(tmp_path):
    controller = build_controller(tmp_path)
    block_root = build_block_root(tmp_path)

    write(block_root / "sda1" / "partition", "1")
    write(block_root / "loop0" / "size", "1000")

    inventory = StorageInventory(
        enclosure=controller,
        topology=TopologyResolver(),
        block_root=block_root,
    )

    devices = {drive.device for drive in inventory.drives()}

    assert "sda1" not in devices
    assert "loop0" not in devices
