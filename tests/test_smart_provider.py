import json
import subprocess

from truepanel.hardware.smart import (
    SmartctlProvider,
    parse_smartctl_json,
)


def completed(payload, returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        args=["smartctl"],
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr=stderr,
    )


def test_parse_ata_smartctl_json():
    telemetry = parse_smartctl_json(
        "sda",
        {
            "smart_status": {"passed": True},
            "temperature": {"current": 38},
            "power_on_time": {"hours": 12345},
            "ata_smart_attributes": {
                "table": [
                    {
                        "name": "Reallocated_Sector_Ct",
                        "raw": {"value": 2},
                    },
                    {
                        "name": "Current_Pending_Sector",
                        "raw": {"value": 0},
                    },
                    {
                        "name": "Offline_Uncorrectable",
                        "raw": {"value": 0},
                    },
                    {
                        "name": "UDMA_CRC_Error_Count",
                        "raw": {"value": 4},
                    },
                ]
            },
        },
    )

    assert telemetry.device == "sda"
    assert telemetry.smart_passed is True
    assert telemetry.temperature_c == 38
    assert telemetry.power_on_hours == 12345
    assert telemetry.reallocated_sectors == 2
    assert telemetry.pending_sectors == 0
    assert telemetry.offline_uncorrectable == 0
    assert telemetry.interface_errors == 4


def test_parse_nvme_smartctl_json():
    telemetry = parse_smartctl_json(
        "/dev/nvme0n1",
        {
            "smart_status": {"passed": True},
            "nvme_smart_health_information_log": {
                "temperature": 42,
                "power_on_hours": 900,
                "percentage_used": 12,
                "available_spare": 100,
            },
        },
    )

    assert telemetry.device == "nvme0n1"
    assert telemetry.temperature_c == 42
    assert telemetry.power_on_hours == 900
    assert telemetry.percentage_used == 12
    assert telemetry.available_spare == 100


def test_provider_invokes_smartctl_with_json():
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return completed({
            "smart_status": {"passed": True},
            "temperature": {"current": 39},
        })

    provider = SmartctlProvider(runner=runner)
    telemetry = provider.collect("/dev/sdb")

    assert calls[0][0] == [
        "smartctl",
        "--json",
        "--all",
        "/dev/sdb",
    ]
    assert telemetry.temperature_c == 39
    assert telemetry.smart_passed is True


def test_missing_smartctl_degrades_to_unknown():
    def runner(command, **kwargs):
        raise FileNotFoundError

    telemetry = SmartctlProvider(runner=runner).collect("sda")

    assert telemetry.source == "unavailable"
    assert telemetry.temperature_c is None
    assert "not installed" in telemetry.message


def test_invalid_json_degrades_to_unknown():
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="not-json",
            stderr="broken",
        )

    telemetry = SmartctlProvider(runner=runner).collect("sda")

    assert telemetry.source == "smartctl"
    assert telemetry.smart_passed is None
    assert telemetry.message == "smartctl returned invalid JSON"
