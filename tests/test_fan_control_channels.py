from truepanel.hardware.fan_runtime import (
    normalize_fan_control_channels,
)


def test_fan_control_channels_default_to_supported_pair():
    assert normalize_fan_control_channels(None) == (
        1,
        2,
    )


def test_fan_control_channels_filter_duplicates_and_unsupported_values():
    assert normalize_fan_control_channels(
        [2, "1", 2, 3, "bad"]
    ) == (
        2,
        1,
    )


def test_fan_control_channels_fail_back_to_supported_pair_when_empty():
    assert normalize_fan_control_channels(
        [3, 4, "bad"]
    ) == (
        1,
        2,
    )
