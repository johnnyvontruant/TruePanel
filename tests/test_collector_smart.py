from collector import TruePanelCollector


def test_smart_health_reports_all_discovered_disks():
    responses = {
        (
            "lsblk -ndo NAME,TYPE | "
            "awk '$2==\"disk\"{print \"/dev/\"$1}'"
        ): "/dev/sda\n/dev/sdf",
        "smartctl -H /dev/sda 2>/dev/null": (
            "SMART overall-health self-assessment "
            "test result: PASSED"
        ),
        "smartctl -A /dev/sda 2>/dev/null": (
            "  5 Reallocated_Sector_Ct "
            "0x0033 100 100 010 Pre-fail "
            "Always - 0"
        ),
        "smartctl -H /dev/sdf 2>/dev/null": (
            "SMART overall-health self-assessment "
            "test result: PASSED"
        ),
        "smartctl -A /dev/sdf 2>/dev/null": (
            "  5 Reallocated_Sector_Ct "
            "0x0033 100 100 010 Pre-fail "
            "Always - 0"
        ),
    }

    collector = TruePanelCollector()
    collector.shell = lambda command: responses.get(
        command,
        "",
    )

    assert collector.get_smart_health() == [
        {
            "drive": "sda",
            "health": "PASSED",
            "reallocated": 0,
            "pending": 0,
            "offline_uncorrectable": 0,
            "reported_uncorrect": 0,
            "media_errors": 0,
            "critical_warning": "0x00",
        },
        {
            "drive": "sdf",
            "health": "PASSED",
            "reallocated": 0,
            "pending": 0,
            "offline_uncorrectable": 0,
            "reported_uncorrect": 0,
            "media_errors": 0,
            "critical_warning": "0x00",
        },
    ]
