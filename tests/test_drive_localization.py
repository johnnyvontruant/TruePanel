from truepanel.hardware.drive_localization import localize_drive_readings


def test_resolves_bay_from_device_name():
    readings = [{"device": "sda", "temperature_c": 45}]
    result = localize_drive_readings(readings, {"sda": 3})

    assert result == [{"device": "sda", "temperature_c": 45, "bay": 3}]


def test_unresolvable_device_gets_explicit_none_not_omission():
    readings = [{"device": "sdz", "temperature_c": 30}]
    result = localize_drive_readings(readings, {"sda": 3})

    assert result[0]["bay"] is None
    assert "bay" in result[0]


def test_falls_back_across_known_device_field_names():
    mapping = {"sda": 1, "sdb": 2, "sdc": 3}

    assert localize_drive_readings([{"drive": "sda"}], mapping)[0]["bay"] == 1
    assert localize_drive_readings([{"disk": "sdb"}], mapping)[0]["bay"] == 2
    assert localize_drive_readings([{"name": "sdc"}], mapping)[0]["bay"] == 3


def test_strips_dev_prefix_before_lookup():
    result = localize_drive_readings([{"device": "/dev/sda"}], {"sda": 4})

    assert result[0]["bay"] == 4


def test_never_overwrites_an_existing_bay_value():
    readings = [{"device": "sda", "bay": 99}]
    result = localize_drive_readings(readings, {"sda": 3})

    assert result[0]["bay"] == 99


def test_empty_or_missing_device_bay_map_preserves_uncertainty():
    readings = [{"device": "sda"}]

    assert localize_drive_readings(readings, {})[0]["bay"] is None
    assert localize_drive_readings(readings, None)[0]["bay"] is None


def test_non_list_input_returns_empty_list_without_raising():
    assert localize_drive_readings(None, {"sda": 1}) == []
    assert localize_drive_readings("not a list", {"sda": 1}) == []


def test_non_dict_entries_pass_through_unchanged():
    readings = [{"device": "sda"}, "malformed", 42, None]
    result = localize_drive_readings(readings, {"sda": 1})

    assert result[0]["bay"] == 1
    assert result[1] == "malformed"
    assert result[2] == 42
    assert result[3] is None


def test_no_device_field_at_all_resolves_to_none():
    readings = [{"temperature_c": 50}]
    result = localize_drive_readings(readings, {"sda": 1})

    assert result[0]["bay"] is None
