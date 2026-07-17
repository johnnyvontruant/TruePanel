"""
Production button monitoring service.

ButtonService converts raw hardware button masks into stable, debounced events.
It deliberately does not own the serial transport. Instead, a caller supplies:

    read_buttons() -> int

This keeps hardware access inside the A125 driver and gives Mission Control a
clean stream of semantic button events.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Deque, Dict, Iterable, Optional, Tuple


LOGGER = logging.getLogger(__name__)


class ButtonAction(Enum):
    PRESSED = "pressed"
    RELEASED = "released"
    HELD = "held"
    REPEATED = "repeated"


@dataclass(frozen=True)
class ButtonDefinition:
    name: str
    mask: int


@dataclass(frozen=True)
class ButtonEvent:
    sequence: int
    button: str
    mask: int
    action: ButtonAction
    timestamp: float
    monotonic_time: float
    held_seconds: float = 0.0
    raw_state: int = 0


@dataclass(frozen=True)
class ButtonServiceSnapshot:
    running: bool
    healthy: bool
    raw_state: int
    stable_state: int
    samples: int
    events: int
    read_errors: int
    consecutive_errors: int
    last_error: Optional[str]
    last_read_time: Optional[float]
    thread_alive: bool


DEFAULT_BUTTONS: Tuple[ButtonDefinition, ...] = (
    ButtonDefinition("enter", 0x01),
    ButtonDefinition("select", 0x02),
)


class ButtonService:
    """
    Poll and debounce a button bitmask provider.

    The reader must return an integer in which each active button is represented
    by a bit. Button definitions convert those bits into semantic names.

    The service accepts an optional ``event_sink`` callback. Mission Control can
    use that callback to enqueue or translate ButtonEvent objects.
    """

    def __init__(
        self,
        read_buttons: Callable[[], int],
        event_sink: Optional[Callable[[ButtonEvent], None]] = None,
        *,
        buttons: Iterable[ButtonDefinition] = DEFAULT_BUTTONS,
        poll_interval: float = 0.075,
        debounce_samples: int = 2,
        long_press_seconds: float = 1.0,
        repeat_delay: Optional[float] = 0.7,
        repeat_interval: Optional[float] = 0.25,
        history_size: int = 100,
        max_consecutive_errors: int = 5,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")

        if debounce_samples < 1:
            raise ValueError("debounce_samples must be at least one")

        if long_press_seconds <= 0:
            raise ValueError("long_press_seconds must be greater than zero")

        if repeat_delay is not None and repeat_delay <= 0:
            raise ValueError("repeat_delay must be greater than zero")

        if repeat_interval is not None and repeat_interval <= 0:
            raise ValueError("repeat_interval must be greater than zero")

        if max_consecutive_errors < 1:
            raise ValueError("max_consecutive_errors must be at least one")

        button_tuple = tuple(buttons)

        if not button_tuple:
            raise ValueError("at least one button definition is required")

        names = [button.name for button in button_tuple]
        masks = [button.mask for button in button_tuple]

        if len(names) != len(set(names)):
            raise ValueError("button names must be unique")

        if len(masks) != len(set(masks)):
            raise ValueError("button masks must be unique")

        for button in button_tuple:
            if not button.name:
                raise ValueError("button names cannot be empty")

            if button.mask <= 0:
                raise ValueError("button masks must be positive")

            if button.mask & (button.mask - 1):
                raise ValueError(
                    f"button mask for {button.name!r} must contain one bit"
                )

        self._read_buttons = read_buttons
        self._event_sink = event_sink
        self._buttons = button_tuple
        self._known_mask = 0

        for button in self._buttons:
            self._known_mask |= button.mask

        self.poll_interval = float(poll_interval)
        self.debounce_samples = int(debounce_samples)
        self.long_press_seconds = float(long_press_seconds)
        self.repeat_delay = repeat_delay
        self.repeat_interval = repeat_interval
        self.max_consecutive_errors = int(max_consecutive_errors)

        self._clock = clock
        self._wall_clock = wall_clock

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._raw_state = 0
        self._candidate_state = 0
        self._candidate_samples = 0
        self._stable_state = 0

        self._press_times: Dict[int, float] = {}
        self._long_press_sent: Dict[int, bool] = {}
        self._next_repeat: Dict[int, float] = {}

        self._sequence = 0
        self._sample_count = 0
        self._event_count = 0
        self._read_errors = 0
        self._consecutive_errors = 0
        self._last_error: Optional[str] = None
        self._last_read_time: Optional[float] = None

        self._history: Deque[ButtonEvent] = deque(maxlen=history_size)

    @property
    def buttons(self) -> Tuple[ButtonDefinition, ...]:
        return self._buttons

    @property
    def stable_state(self) -> int:
        with self._lock:
            return self._stable_state

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """
        Start the polling thread.

        Returns True when a new thread was started and False when the service
        was already running.
        """

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="truepanel-button-service",
                daemon=True,
            )
            self._thread.start()

        return True

    def stop(self, timeout: float = 2.0) -> bool:
        """
        Stop the polling thread.

        Returns True when the thread stopped cleanly.
        """

        self._stop_event.set()

        with self._lock:
            thread = self._thread

        if thread is None:
            return True

        if thread is threading.current_thread():
            return False

        thread.join(timeout=max(0.0, timeout))
        stopped = not thread.is_alive()

        if stopped:
            with self._lock:
                if self._thread is thread:
                    self._thread = None

        return stopped

    def poll_once(self) -> Tuple[ButtonEvent, ...]:
        """
        Perform one hardware read and state-machine update.

        Exposed for deterministic tests and cooperative/non-threaded callers.
        """

        try:
            value = self._read_buttons()

            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(
                    "button reader must return an integer bitmask, "
                    f"got {type(value).__name__}"
                )

            if value < 0:
                raise ValueError("button reader returned a negative bitmask")

        except Exception as exc:
            with self._lock:
                self._read_errors += 1
                self._consecutive_errors += 1
                self._last_error = f"{type(exc).__name__}: {exc}"

            LOGGER.warning("Button read failed: %s", exc)
            return ()

        now = self._clock()

        with self._lock:
            self._sample_count += 1
            self._last_read_time = self._wall_clock()
            self._consecutive_errors = 0
            self._last_error = None
            self._raw_state = value

            events = list(self._consume_sample(value, now))
            events.extend(self._held_events(now))

        for event in events:
            self._deliver(event)

        return tuple(events)

    def history(self) -> Tuple[ButtonEvent, ...]:
        with self._lock:
            return tuple(self._history)

    def snapshot(self) -> ButtonServiceSnapshot:
        with self._lock:
            thread_alive = self._thread is not None and self._thread.is_alive()

            return ButtonServiceSnapshot(
                running=thread_alive and not self._stop_event.is_set(),
                healthy=(
                    self._consecutive_errors < self.max_consecutive_errors
                ),
                raw_state=self._raw_state,
                stable_state=self._stable_state,
                samples=self._sample_count,
                events=self._event_count,
                read_errors=self._read_errors,
                consecutive_errors=self._consecutive_errors,
                last_error=self._last_error,
                last_read_time=self._last_read_time,
                thread_alive=thread_alive,
            )

    def reset(self) -> None:
        """
        Reset debounce and held-button state.

        Metrics and event history are intentionally preserved.
        """

        with self._lock:
            self._raw_state = 0
            self._candidate_state = 0
            self._candidate_samples = 0
            self._stable_state = 0
            self._press_times.clear()
            self._long_press_sent.clear()
            self._next_repeat.clear()

    def _run(self) -> None:
        LOGGER.info("ButtonService started")

        try:
            while not self._stop_event.is_set():
                started = self._clock()
                self.poll_once()
                elapsed = self._clock() - started
                delay = max(0.0, self.poll_interval - elapsed)
                self._stop_event.wait(delay)
        finally:
            LOGGER.info("ButtonService stopped")

    def _consume_sample(
        self,
        raw_state: int,
        now: float,
    ) -> Tuple[ButtonEvent, ...]:
        if raw_state == self._stable_state:
            self._candidate_state = raw_state
            self._candidate_samples = 0
            return ()

        if raw_state != self._candidate_state:
            self._candidate_state = raw_state
            self._candidate_samples = 1
        else:
            self._candidate_samples += 1

        if self._candidate_samples < self.debounce_samples:
            return ()

        previous = self._stable_state
        self._stable_state = self._candidate_state
        self._candidate_samples = 0

        changed = previous ^ self._stable_state
        events = []

        for button in self._buttons:
            if not changed & button.mask:
                continue

            if self._stable_state & button.mask:
                self._press_times[button.mask] = now
                self._long_press_sent[button.mask] = False

                if self.repeat_delay is not None:
                    self._next_repeat[button.mask] = now + self.repeat_delay

                events.append(
                    self._make_event(
                        button,
                        ButtonAction.PRESSED,
                        now,
                    )
                )
            else:
                press_time = self._press_times.pop(button.mask, now)
                held_seconds = max(0.0, now - press_time)
                self._long_press_sent.pop(button.mask, None)
                self._next_repeat.pop(button.mask, None)

                events.append(
                    self._make_event(
                        button,
                        ButtonAction.RELEASED,
                        now,
                        held_seconds=held_seconds,
                    )
                )

        return tuple(events)

    def _held_events(self, now: float) -> Tuple[ButtonEvent, ...]:
        events = []

        for button in self._buttons:
            if not self._stable_state & button.mask:
                continue

            press_time = self._press_times.get(button.mask)

            if press_time is None:
                continue

            held_seconds = max(0.0, now - press_time)

            if (
                held_seconds >= self.long_press_seconds
                and not self._long_press_sent.get(button.mask, False)
            ):
                self._long_press_sent[button.mask] = True
                events.append(
                    self._make_event(
                        button,
                        ButtonAction.HELD,
                        now,
                        held_seconds=held_seconds,
                    )
                )

            next_repeat = self._next_repeat.get(button.mask)

            if (
                self.repeat_interval is not None
                and next_repeat is not None
                and now >= next_repeat
            ):
                events.append(
                    self._make_event(
                        button,
                        ButtonAction.REPEATED,
                        now,
                        held_seconds=held_seconds,
                    )
                )

                while next_repeat <= now:
                    next_repeat += self.repeat_interval

                self._next_repeat[button.mask] = next_repeat

        return tuple(events)

    def _make_event(
        self,
        button: ButtonDefinition,
        action: ButtonAction,
        now: float,
        *,
        held_seconds: float = 0.0,
    ) -> ButtonEvent:
        self._sequence += 1

        return ButtonEvent(
            sequence=self._sequence,
            button=button.name,
            mask=button.mask,
            action=action,
            timestamp=self._wall_clock(),
            monotonic_time=now,
            held_seconds=held_seconds,
            raw_state=self._stable_state,
        )

    def _deliver(self, event: ButtonEvent) -> None:
        with self._lock:
            self._history.append(event)
            self._event_count += 1
            event_sink = self._event_sink

        if event_sink is None:
            return

        try:
            event_sink(event)
        except Exception:
            LOGGER.exception(
                "Button event sink failed for %s/%s",
                event.button,
                event.action.value,
            )
