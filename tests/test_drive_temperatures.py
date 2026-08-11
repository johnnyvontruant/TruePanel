from truepanel.hardware.drive_temperatures import (
    DriveTemperatureProvider,
    parse_legacy_smart_temperature,
)


def test_parses_ata_temperature_attribute():
    output = """
194 Temperature_Celsius 0x0022 062 050 000 Old_age Always - 38
"""

    assert (
        parse_legacy_smart_temperature(
            output
        )
        == 38
    )


def test_parses_temperature_line():
    output = """
Temperature:                        47 Celsius
"""

    assert (
        parse_legacy_smart_temperature(
            output
        )
        == 47
    )


def test_unrecognized_temperature_is_missing():
    assert (
        parse_legacy_smart_temperature(
            "Nothing useful here"
        )
        is None
    )


def test_provider_preserves_legacy_population():
    responses = {
        (
            "lsblk -ndo NAME,TYPE | "
            "awk '$2==\"disk\""
            "{print \"/dev/\"$1}'"
        ): (
            "/dev/sda\n"
            "/dev/sdb\n"
            "/dev/sdf\n"
        ),
        (
            "smartctl -a /dev/sda "
            "2>/dev/null"
        ): "Unrecognized temperature",
        (
            "smartctl -a /dev/sdb "
            "2>/dev/null"
        ): (
            "194 Temperature_Celsius "
            "0x0022 062 050 000 "
            "Old_age Always - 38"
        ),
    }

    provider = DriveTemperatureProvider(
        runner=lambda command: (
            responses.get(
                command,
                "",
            )
        ),
    )

    assert provider.records() == [
        {
            "drive": "sdb",
            "temp": 38,
        }
    ]

    assert provider.temperatures() == (
        38.0,
    )
