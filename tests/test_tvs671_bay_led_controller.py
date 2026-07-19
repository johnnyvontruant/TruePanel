import pytest

from truepanel.hardware.bay_leds import (
    TVS671BayLedController,
)


def test_verified_identify_command_map():
    expected = {
        1: (0x02, 0x03),
        2: (0x04, 0x05),
        3: (0x06, 0x07),
        4: (0x08, 0x09),
        5: (0x0A, 0x0B),
        6: (0x0C, 0x0D),
    }

    for bay, commands in expected.items():
        assert (
            TVS671BayLedController.identify_command(
                bay,
                True,
            )
            == commands[0]
        )
        assert (
            TVS671BayLedController.identify_command(
                bay,
                False,
            )
            == commands[1]
        )


def test_controller_suppresses_duplicate_writes():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )

    assert controller.set_identify(1, True)
    assert not controller.set_identify(1, True)
    assert controller.set_identify(1, False)

    assert commands == [0x02, 0x03]
    assert controller.active_bays == ()


def test_controller_tracks_multiple_active_bays():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )

    controller.set_identify(2, True)
    controller.set_identify(5, True)

    assert commands == [0x04, 0x0A]
    assert controller.active_bays == (2, 5)


def test_controller_rejects_invalid_bay():
    controller = TVS671BayLedController(
        command_writer=lambda command: None
    )

    with pytest.raises(ValueError):
        controller.set_identify(7, True)
