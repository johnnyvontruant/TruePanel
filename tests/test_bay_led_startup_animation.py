from truepanel.hardware.bay_led_animation import (
    BayLedStartupAnimation,
    build_bay_led_startup_animation,
    get_bay_led_animation_config,
)


class FakeController:
    def __init__(self):
        self.calls = []
        self.cleared = 0

    def set_identify(
        self,
        bay,
        enabled,
        *,
        force=False,
    ):
        self.calls.append(
            (
                bay,
                enabled,
                force,
            )
        )
        return True

    def clear_all(self):
        self.cleared += 1


def test_animation_sequence():
    controller = FakeController()
    delays = []

    animation = BayLedStartupAnimation(
        controller,
        step_delay=0.1,
        pulse_hold=0.4,
        sleeper=delays.append,
    )

    animation.run()

    expected = []

    for bay in range(1, 7):
        expected.append(
            (
                bay,
                True,
                True,
            )
        )

    for bay in range(6, 0, -1):
        expected.append(
            (
                bay,
                False,
                True,
            )
        )

    for bay in range(1, 7):
        expected.append(
            (
                bay,
                True,
                True,
            )
        )

    assert controller.calls == expected
    assert controller.cleared == 1
    assert delays == (
        [0.1] * 12
        + [0.4]
    )


def test_animation_clears_after_failure():
    class FailingController(
        FakeController
    ):
        def set_identify(
            self,
            bay,
            enabled,
            *,
            force=False,
        ):
            super().set_identify(
                bay,
                enabled,
                force=force,
            )

            if bay == 3 and enabled:
                raise RuntimeError(
                    "simulated failure"
                )

            return True

    controller = FailingController()

    animation = BayLedStartupAnimation(
        controller,
        step_delay=0,
        pulse_hold=0,
        sleeper=lambda seconds: None,
    )

    animation.run()

    assert controller.cleared == 1
    assert len(controller.calls) == 18


def test_disabled_factory_returns_none():
    assert (
        build_bay_led_startup_animation(
            {
                "startup": {
                    "bay_led_animation": {
                        "enabled": False,
                    }
                }
            }
        )
        is None
    )


def test_factory_reads_settings():
    controller = FakeController()

    animation = build_bay_led_startup_animation(
        {
            "flightdeck": {
                "startup": {
                    "bay_led_animation": {
                        "enabled": True,
                        "step_delay": 0.2,
                        "pulse_hold": 0.5,
                        "clear_when_finished": False,
                    }
                }
            }
        },
        controller=controller,
        sleeper=lambda seconds: None,
    )

    assert animation is not None
    assert animation.controller is controller
    assert animation.step_delay == 0.2
    assert animation.pulse_hold == 0.5
    assert animation.clear_when_finished is False


def test_partial_config_retains_defaults():
    settings = get_bay_led_animation_config(
        {
            "flightdeck": {
                "startup": {
                    "bay_led_animation": {
                        "enabled": True,
                    }
                }
            }
        }
    )

    assert settings["enabled"] is True
    assert settings["step_delay"] == 1.0
    assert settings["pulse_hold"] == 0.35
    assert settings["clear_when_finished"] is True


def test_project_default_config_contains_animation_settings():
    from truepanel.config.loader import DEFAULT_CONFIG

    settings = DEFAULT_CONFIG[
        "flightdeck"
    ]["startup"]["bay_led_animation"]

    assert settings == {
        "enabled": False,
        "step_delay": 1.0,
        "pulse_hold": 0.35,
        "clear_when_finished": True,
    }
