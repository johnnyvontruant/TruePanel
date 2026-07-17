import time
import unittest

from truepanel.mission_control.button_service import (
    ButtonAction,
    ButtonDefinition,
    ButtonService,
)


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class SequenceReader:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def __call__(self):
        if not self.values:
            return 0

        if self.index >= len(self.values):
            return self.values[-1]

        value = self.values[self.index]
        self.index += 1

        if isinstance(value, Exception):
            raise value

        return value


class ButtonServiceTests(unittest.TestCase):
    def make_service(
        self,
        values,
        *,
        debounce_samples=2,
        repeat_delay=None,
        repeat_interval=None,
    ):
        clock = FakeClock()
        events = []

        service = ButtonService(
            SequenceReader(values),
            events.append,
            buttons=(
                ButtonDefinition("enter", 0x01),
                ButtonDefinition("select", 0x02),
            ),
            debounce_samples=debounce_samples,
            long_press_seconds=1.0,
            repeat_delay=repeat_delay,
            repeat_interval=repeat_interval,
            clock=clock,
            wall_clock=clock,
        )

        return service, clock, events

    def test_debounces_press_and_release(self):
        service, clock, events = self.make_service(
            [0x00, 0x01, 0x00, 0x01, 0x01, 0x00, 0x00]
        )

        for _ in range(7):
            service.poll_once()
            clock.advance(0.1)

        self.assertEqual(
            [event.action for event in events],
            [ButtonAction.PRESSED, ButtonAction.RELEASED],
        )
        self.assertEqual(events[0].button, "enter")
        self.assertEqual(service.stable_state, 0)

    def test_simultaneous_buttons_are_independent(self):
        service, clock, events = self.make_service(
            [0x03, 0x03],
        )

        service.poll_once()
        clock.advance(0.1)
        service.poll_once()

        self.assertEqual(len(events), 2)
        self.assertEqual(
            {event.button for event in events},
            {"enter", "select"},
        )
        self.assertTrue(
            all(event.action is ButtonAction.PRESSED for event in events)
        )

    def test_long_press_emitted_once(self):
        service, clock, events = self.make_service(
            [0x01, 0x01, 0x01, 0x01],
        )

        service.poll_once()
        clock.advance(0.1)
        service.poll_once()

        clock.advance(1.0)
        service.poll_once()

        clock.advance(1.0)
        service.poll_once()

        actions = [event.action for event in events]

        self.assertEqual(actions.count(ButtonAction.PRESSED), 1)
        self.assertEqual(actions.count(ButtonAction.HELD), 1)

    def test_repeat_events(self):
        service, clock, events = self.make_service(
            [0x01, 0x01, 0x01, 0x01],
            repeat_delay=0.5,
            repeat_interval=0.25,
        )

        service.poll_once()
        clock.advance(0.1)
        service.poll_once()

        clock.advance(0.5)
        service.poll_once()

        clock.advance(0.25)
        service.poll_once()

        actions = [event.action for event in events]

        self.assertEqual(actions.count(ButtonAction.PRESSED), 1)
        self.assertEqual(actions.count(ButtonAction.REPEATED), 2)

    def test_reader_errors_are_isolated(self):
        service, clock, events = self.make_service(
            [RuntimeError("serial unavailable"), 0x00]
        )

        self.assertEqual(service.poll_once(), ())
        snapshot = service.snapshot()

        self.assertEqual(snapshot.read_errors, 1)
        self.assertEqual(snapshot.consecutive_errors, 1)
        self.assertIn("serial unavailable", snapshot.last_error)

        clock.advance(0.1)
        service.poll_once()
        snapshot = service.snapshot()

        self.assertEqual(snapshot.consecutive_errors, 0)
        self.assertIsNone(snapshot.last_error)
        self.assertEqual(events, [])

    def test_invalid_reader_value_counts_as_error(self):
        service, _, _ = self.make_service(["pressed"])

        service.poll_once()
        snapshot = service.snapshot()

        self.assertEqual(snapshot.read_errors, 1)
        self.assertIn("TypeError", snapshot.last_error)

    def test_thread_lifecycle_is_idempotent(self):
        service = ButtonService(
            lambda: 0,
            poll_interval=0.01,
            debounce_samples=1,
        )

        self.assertTrue(service.start())
        self.assertFalse(service.start())

        time.sleep(0.03)

        self.assertTrue(service.snapshot().thread_alive)
        self.assertTrue(service.stop(timeout=1.0))
        self.assertTrue(service.stop(timeout=1.0))
        self.assertFalse(service.snapshot().thread_alive)


if __name__ == "__main__":
    unittest.main()
