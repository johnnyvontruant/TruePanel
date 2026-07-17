from dataclasses import dataclass
from pathlib import Path

import pytest

from truepanel.hardware.health import StorageHealthService
from truepanel.hardware.inventory import Drive, StorageDevice
from truepanel.hardware.telemetry import HealthState, StorageTelemetry


def make_entry(
    device="sda",
    *,
    label="Bay 1",
    bay=1,
    transport="sata",
):
    drive = Drive(
        device=device,
        model="Test Drive",
        serial=f"SERIAL-{device}",
        transport=transport,
        removable=False,
        size_bytes=1_000_000,
        sysfs_path=Path(f"/sys/class/block/{device}"),
    )

    return StorageDevice(
        drive=drive,
        category="front-bay" if bay else "internal-nvme",
        label=label,
        physical_bay=bay,
    )


class FakeInventory:
    def __init__(self, entries):
        self.entries = entries

    def devices(self):
        return list(self.entries)


class FakeProvider:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def collect(self, device):
        self.calls.append(device)
        return self.records[device]


def service_for(telemetry):
    entry = make_entry(telemetry.device)
    provider = FakeProvider({telemetry.device: telemetry})

    return StorageHealthService(
        FakeInventory([entry]),
        provider,
    )


def test_healthy_device():
    service = service_for(
        StorageTelemetry(
            device="sda",
            temperature_c=38,
            smart_passed=True,
            pending_sectors=0,
            offline_uncorrectable=0,
            reallocated_sectors=0,
            interface_errors=0,
            source="smartctl",
        )
    )

    record = service.devices()[0]

    assert record.state is HealthState.HEALTHY
    assert record.message == "healthy"
    assert record.label == "Bay 1"


def test_failed_smart_is_critical():
    service = service_for(
        StorageTelemetry(
            device="sda",
            smart_passed=False,
            temperature_c=30,
        )
    )

    record = service.devices()[0]

    assert record.state is HealthState.CRITICAL
    assert "SMART" in record.message


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pending_sectors", 1),
        ("offline_uncorrectable", 2),
    ],
)
def test_unreadable_sectors_are_critical(field, value):
    telemetry = StorageTelemetry(
        device="sda",
        smart_passed=True,
        **{field: value},
    )

    record = service_for(telemetry).devices()[0]

    assert record.state is HealthState.CRITICAL


def test_hot_drive_is_warning():
    record = service_for(
        StorageTelemetry(
            device="sda",
            smart_passed=True,
            temperature_c=47,
        )
    ).devices()[0]

    assert record.state is HealthState.WARNING
    assert "47°C" in record.message


def test_very_hot_drive_is_critical():
    record = service_for(
        StorageTelemetry(
            device="sda",
            smart_passed=True,
            temperature_c=58,
        )
    ).devices()[0]

    assert record.state is HealthState.CRITICAL


def test_reallocated_sectors_are_warning():
    record = service_for(
        StorageTelemetry(
            device="sda",
            smart_passed=True,
            reallocated_sectors=3,
        )
    ).devices()[0]

    assert record.state is HealthState.WARNING
    assert "reallocated" in record.message


def test_missing_telemetry_is_unknown():
    record = service_for(
        StorageTelemetry(
            device="sda",
            source="unavailable",
            message="smartctl is not installed",
        )
    ).devices()[0]

    assert record.state is HealthState.UNKNOWN
    assert "not installed" in record.message


def test_find_device_and_bay():
    entries = [
        make_entry("sda", label="Bay 1", bay=1),
        make_entry(
            "nvme0n1",
            label="Internal NVMe 1",
            bay=None,
            transport="nvme",
        ),
    ]

    provider = FakeProvider({
        "sda": StorageTelemetry(
            device="sda",
            temperature_c=38,
        ),
        "nvme0n1": StorageTelemetry(
            device="nvme0n1",
            temperature_c=40,
        ),
    })

    service = StorageHealthService(
        FakeInventory(entries),
        provider,
    )

    assert service.find_device("/dev/nvme0n1").label == "Internal NVMe 1"
    assert service.find_bay(1).device == "sda"
    assert service.find_bay(99) is None


def test_summary_counts_health_states():
    entries = [
        make_entry("sda", label="Bay 1", bay=1),
        make_entry("sdb", label="Bay 2", bay=2),
        make_entry("sdc", label="Bay 3", bay=3),
    ]

    provider = FakeProvider({
        "sda": StorageTelemetry(
            device="sda",
            smart_passed=True,
            temperature_c=35,
        ),
        "sdb": StorageTelemetry(
            device="sdb",
            smart_passed=True,
            temperature_c=48,
        ),
        "sdc": StorageTelemetry(
            device="sdc",
            smart_passed=False,
        ),
    })

    summary = StorageHealthService(
        FakeInventory(entries),
        provider,
    ).summary()

    assert summary == {
        "healthy": 1,
        "warning": 1,
        "critical": 1,
        "unknown": 0,
        "total": 3,
    }


def test_invalid_temperature_thresholds_are_rejected():
    with pytest.raises(
        ValueError,
        match="critical temperature",
    ):
        StorageHealthService(
            FakeInventory([]),
            FakeProvider({}),
            warning_temperature_c=55,
            critical_temperature_c=55,
        )
