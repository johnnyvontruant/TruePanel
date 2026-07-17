import argparse
import json
from datetime import datetime, timezone

from truepanel.hardware.commands import (
    add_hardware_subcommands,
    handle_hardware_command,
)
from truepanel.hardware.health_commands import (
    build_health_report,
    health_record_to_dict,
)
from truepanel.hardware.telemetry import (
    HealthState,
    StorageHealthRecord,
    StorageTelemetry,
)


def make_record(
    device,
    label,
    state,
    *,
    bay=None,
    temperature=38,
    smart_passed=True,
    message="healthy",
):
    telemetry = StorageTelemetry(
        device=device,
        temperature_c=temperature,
        smart_passed=smart_passed,
        power_on_hours=1200,
        reallocated_sectors=0,
        pending_sectors=0,
        offline_uncorrectable=0,
        interface_errors=0,
        percentage_used=5 if device.startswith("nvme") else None,
        available_spare=100 if device.startswith("nvme") else None,
        source="smartctl",
        collected_at=datetime(
            2026,
            7,
            17,
            16,
            0,
            tzinfo=timezone.utc,
        ),
    )

    return StorageHealthRecord(
        device=device,
        label=label,
        category=(
            "front-bay"
            if bay is not None
            else "internal-nvme"
        ),
        physical_bay=bay,
        serial=f"SERIAL-{device}",
        model="Test Drive",
        transport=(
            "nvme"
            if device.startswith("nvme")
            else "sata"
        ),
        telemetry=telemetry,
        state=state,
        message=message,
    )


class FakeHealthService:
    def __init__(self):
        self.records = [
            make_record(
                "sda",
                "Bay 1",
                HealthState.HEALTHY,
                bay=1,
                temperature=38,
            ),
            make_record(
                "sdf",
                "Bay 5",
                HealthState.WARNING,
                bay=5,
                temperature=47,
                message="temperature 47°C",
            ),
            make_record(
                "nvme0n1",
                "Internal NVMe 1",
                HealthState.CRITICAL,
                temperature=58,
                smart_passed=False,
                message="SMART self-assessment failed",
            ),
        ]

    def devices(self):
        return list(self.records)

    def find_device(self, device):
        name = device.removeprefix("/dev/")
        return next(
            (
                record
                for record in self.records
                if record.device == name
            ),
            None,
        )

    def find_bay(self, bay):
        return next(
            (
                record
                for record in self.records
                if record.physical_bay == bay
            ),
            None,
        )

    def by_state(self, state):
        target = HealthState(state)
        return [
            record
            for record in self.records
            if record.state is target
        ]


class FakeHardwareManager:
    def __init__(self):
        self.health = FakeHealthService()


def build_parser():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command")
    add_hardware_subcommands(subcommands)
    return parser


def test_record_serializes_enums_and_datetime():
    record = FakeHealthService().records[0]
    payload = health_record_to_dict(record)

    assert payload["state"] == "healthy"
    assert payload["device_path"] == "/dev/sda"
    assert payload["temperature_c"] == 38
    assert payload["telemetry"]["collected_at"] == (
        "2026-07-17T16:00:00+00:00"
    )


def test_health_report_contains_summary():
    report = build_health_report(FakeHardwareManager())

    assert report["device_count"] == 3
    assert report["summary"] == {
        "healthy": 1,
        "warning": 1,
        "critical": 1,
        "unknown": 0,
        "total": 3,
    }


def test_health_device_filter_accepts_dev_path():
    report = build_health_report(
        FakeHardwareManager(),
        device="/dev/sdf",
    )

    assert report["device_count"] == 1
    assert report["devices"][0]["label"] == "Bay 5"


def test_health_bay_filter():
    report = build_health_report(
        FakeHardwareManager(),
        bay=1,
    )

    assert report["device_count"] == 1
    assert report["devices"][0]["device"] == "sda"


def test_health_state_filter():
    report = build_health_report(
        FakeHardwareManager(),
        state="critical",
    )

    assert report["device_count"] == 1
    assert report["devices"][0]["device"] == "nvme0n1"


def test_health_human_output(capsys):
    parser = build_parser()
    args = parser.parse_args(["hardware", "health"])

    handled = handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )

    output = capsys.readouterr().out

    assert handled is True
    assert "TruePanel Storage Health" in output
    assert "Healthy  : 1" in output
    assert "Warning  : 1" in output
    assert "Critical : 1" in output
    assert "Bay 1" in output
    assert "/dev/sda" in output
    assert "38°C" in output
    assert "HEALTHY" in output


def test_health_verbose_output(capsys):
    parser = build_parser()
    args = parser.parse_args(
        ["hardware", "health", "--verbose"]
    )

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )

    output = capsys.readouterr().out

    assert "SMART Assessment  : PASS" in output
    assert "Power-On Hours    : 1200" in output
    assert "Reallocated       : 0" in output
    assert "Source            : smartctl" in output


def test_health_json_output(capsys):
    parser = build_parser()
    args = parser.parse_args(
        ["hardware", "health", "--json"]
    )

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["device_count"] == 3
    assert payload["summary"]["critical"] == 1
    assert payload["devices"][0]["state"] == "healthy"


def test_health_cli_device_filter(capsys):
    parser = build_parser()
    args = parser.parse_args(
        [
            "hardware",
            "health",
            "--device",
            "/dev/sdf",
        ]
    )

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )

    output = capsys.readouterr().out

    assert "Bay 5" in output
    assert "Bay 1" not in output


def test_health_cli_missing_device(capsys):
    parser = build_parser()
    args = parser.parse_args(
        [
            "hardware",
            "health",
            "--device",
            "sdz",
        ]
    )

    handle_hardware_command(
        args,
        manager=FakeHardwareManager(),
    )

    output = capsys.readouterr().out

    assert "No matching storage devices." in output
