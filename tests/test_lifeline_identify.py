from truepanel.lifeline import BayIdentificationService


class Controller:
    def __init__(self):
        self.calls = []

    @staticmethod
    def validate_bay(bay):
        bay = int(bay)
        if not 1 <= bay <= 6:
            raise ValueError("bad bay")
        return bay

    def set_identify(self, bay, enabled, *, force=False):
        self.calls.append((bay, enabled, force))
        return True


class Timer:
    def __init__(self, seconds, callback, args=()):
        self.seconds = seconds
        self.callback = callback
        self.args = args
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback(*self.args)


class TimerFactory:
    def __init__(self):
        self.timers = []

    def __call__(self, seconds, callback, args=()):
        timer = Timer(seconds, callback, args=args)
        self.timers.append(timer)
        return timer


def test_identify_flashes_only_requested_verified_bay():
    controller = Controller()
    timers = TimerFactory()
    service = BayIdentificationService(
        controller=controller,
        timer_factory=timers,
        default_seconds=15,
    )

    result = service.identify(3)

    assert controller.calls == [(3, True, True)]
    assert result == {
        "bay": 3,
        "identify": True,
        "duration_seconds": 15.0,
        "storage_mutation": False,
        "hardware_action": "identify_led",
    }
    assert timers.timers[0].started is True
    assert timers.timers[0].daemon is True


def test_identify_auto_clear_turns_same_bay_off():
    controller = Controller()
    timers = TimerFactory()
    service = BayIdentificationService(
        controller=controller,
        timer_factory=timers,
    )

    service.identify(3)
    timers.timers[0].fire()

    assert controller.calls == [
        (3, True, True),
        (3, False, True),
    ]


def test_reidentifying_same_bay_cancels_old_timer():
    controller = Controller()
    timers = TimerFactory()
    service = BayIdentificationService(
        controller=controller,
        timer_factory=timers,
    )

    service.identify(3)
    first = timers.timers[0]
    service.identify(3)

    assert first.cancelled is True
    assert controller.calls == [
        (3, True, True),
        (3, True, True),
    ]


def test_duration_is_bounded_even_for_internal_callers():
    controller = Controller()
    timers = TimerFactory()
    service = BayIdentificationService(
        controller=controller,
        timer_factory=timers,
    )

    result = service.identify(3, seconds=999)

    assert result["duration_seconds"] == 60.0
    assert timers.timers[0].seconds == 60.0


def test_invalid_bay_is_rejected_before_led_write():
    controller = Controller()
    service = BayIdentificationService(controller=controller)

    try:
        service.identify(9)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid bay unexpectedly accepted")

    assert controller.calls == []
