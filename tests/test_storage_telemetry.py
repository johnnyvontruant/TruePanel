from truepanel.hardware.telemetry import (
    HealthState,
    StorageHealthRecord,
    StorageTelemetry,
)


def test_storage_telemetry_device_path():
    telemetry = StorageTelemetry(
        device="sda",
        temperature_c=38,
        source="smartctl",
    )

    assert telemetry.device_path == "/dev/sda"
    assert telemetry.temperature_c == 38


def test_storage_health_record_exposes_common_values():
    telemetry = StorageTelemetry(
        device="nvme0n1",
        temperature_c=41,
        smart_passed=True,
        source="smartctl",
    )

    record = StorageHealthRecord(
        device="nvme0n1",
        label="Internal NVMe 1",
        category="internal-nvme",
        physical_bay=None,
        serial="NVME1",
        model="Samsung NVMe",
        transport="nvme",
        telemetry=telemetry,
        state=HealthState.HEALTHY,
        message="healthy",
    )

    assert record.device_path == "/dev/nvme0n1"
    assert record.temperature_c == 41
    assert record.smart_passed is True
    assert record.source == "smartctl"
