from __future__ import annotations

import json

from truepanel.loadmaster.capacity import (
    DAY,
    CapacityLog,
    check_disk,
    disk_of,
    forecast,
    parse_smart,
    read_smart,
)

TB = 10**12


def test_parse_smart_reads_status_temperature_and_wear():
    nvme = {
        "smart_status": {"passed": True},
        "model_name": "Micron CT8000X10SSD9",
        "temperature": {"current": 41},
        "power_on_time": {"hours": 1200},
        "nvme_smart_health_information_log": {"percentage_used": 3},
    }
    assert parse_smart(nvme) == {
        "status": "PASSED",
        "model": "Micron CT8000X10SSD9",
        "temperature_c": 41,
        "power_on_hours": 1200,
        "percent_used": 3,
    }
    ata = {
        "smart_status": {"passed": False},
        "ata_smart_attributes": {
            "table": [{"id": 9, "value": 99}, {"id": 202, "value": 94}]
        },
    }
    assert (
        parse_smart(ata)["status"] == "FAILED" and parse_smart(ata)["percent_used"] == 6
    )
    assert parse_smart({"device": {"name": "/dev/sda"}}) is None  # SMART not readable


def test_model_from_scsi_fields_then_lsblk():
    passed = {"smart_status": {"passed": True}}
    assert (
        parse_smart({**passed, "scsi_vendor": "Samsung", "scsi_product": "PSSD T7"})[
            "model"
        ]
        == "Samsung PSSD T7"
    )
    assert (
        parse_smart({**passed, "scsi_model_name": "WD Elements"})["model"]
        == "WD Elements"
    )

    calls = []

    def runner(argv):
        calls.append(argv)
        if argv[:3] == ["lsblk", "-no", "PKNAME"]:
            return "sdh\n"
        if argv[:3] == ["lsblk", "-dno", "MODEL"]:
            return "Portable SSD T7  \n"
        return json.dumps(passed)

    health = check_disk("/dev/sdh1", runner)
    assert health["model"] == "Portable SSD T7" and calls[-1][-1] == "/dev/sdh"

    def unreadable(argv):
        return "sdh" if argv[0] == "lsblk" else "{}"

    assert check_disk("/dev/sdh1", unreadable) == {"status": "unavailable"}


def test_read_smart_falls_back_to_sat_then_gives_up():
    calls = []

    def runner(argv):
        calls.append(argv)
        return json.dumps({"smart_status": {"passed": True}} if "sat" in argv else {})

    assert read_smart("/dev/sda", runner)["status"] == "PASSED"
    assert calls[1][-3:] == ["-d", "sat", "/dev/sda"]

    def broken(argv):
        raise FileNotFoundError("smartctl")

    assert read_smart("/dev/sda", broken) == {"status": "unavailable"}
    assert disk_of("/dev/sda2", lambda argv: "sda\n") == "/dev/sda"
    assert disk_of("/dev/sda2", broken) == "/dev/sda2"


def test_forecast_needs_history_and_growth():
    now = 100 * DAY
    capacity = 8 * TB
    growing = [
        (now - 30 * DAY + d * DAY, int(6 * TB + d * 10**10)) for d in range(31)
    ]  # 10 GB/day
    days = forecast(growing, capacity, now)
    room = capacity * 0.98 - growing[-1][1]
    assert abs(days - room / 10**10) < 0.5
    assert forecast(growing[-1:], capacity, now) is None  # one sample
    assert forecast([(now - DAY, 1), (now, 2)], capacity, now) is None  # under 3 days
    assert (
        forecast([(now - 10 * DAY, 5), (now, 5)], capacity, now) is None
    )  # not growing
    old = [(t - 90 * DAY, b) for t, b in growing]
    assert forecast(old, capacity, now) is None  # outside the 60-day window


def test_capacity_log_samples_daily_and_summarises(tmp_path):
    clock = [10 * DAY]
    log = CapacityLog(tmp_path, clock=lambda: clock[0])
    assert log.summary("TV A-M") == {}
    assert log.record_nas("TV A-M", 6 * TB)
    assert not log.record_nas("TV A-M", 6 * TB + 1)  # same day
    clock[0] += 5 * DAY
    assert log.record_nas("TV A-M", 6 * TB + 5 * 10**10)
    log.record_drive(
        "TV A-M", capacity_bytes=8 * TB, free_bytes=2 * TB, smart={"status": "PASSED"}
    )

    summary = log.summary("TV A-M")
    assert summary["capacity_bytes"] == 8 * TB and summary["smart"] == {
        "status": "PASSED"
    }
    assert round(summary["used_fraction"], 3) == round(
        (6 * TB + 5 * 10**10) / (8 * TB), 3
    )
    assert 175 < summary["full_in_days"] < 185  # 10 GB/day with ~1.79 TB left: 179 days
    assert log.summary("TV N-Z") == {}
