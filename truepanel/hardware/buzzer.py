"""
TruePanel buzzer support.

Uses Linux's PC-speaker input interface when available. This communicates
through the pcspkr kernel driver and does not share the LCD serial port.
"""

import glob
import logging
import os
import struct
import threading
import time


LOGGER = logging.getLogger("truepanel.buzzer")

EV_SND = 0x12
SND_TONE = 0x02


class Buzzer:
    def __init__(self, config=None, connection=None):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.backend = str(self.config.get("backend", "pcspkr"))
        self.device = self.config.get("device", "auto")
        self.cooldown = float(self.config.get("cooldown", 30))

        self.short_frequency = int(
            self.config.get("short_frequency", 880)
        )
        self.short_duration = float(
            self.config.get("short_duration", 0.2)
        )

        self.long_frequency = int(
            self.config.get("long_frequency", 660)
        )
        self.long_duration = float(
            self.config.get("long_duration", 0.65)
        )

        self.last_beep = 0.0
        self.lock = threading.Lock()

    @staticmethod
    def _device_name(path):
        try:
            event_name = os.path.basename(os.path.realpath(path))
            name_path = f"/sys/class/input/{event_name}/device/name"

            with open(name_path, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError:
            return ""

    def find_device(self):
        if self.device not in ("", "auto", None):
            return self.device if os.path.exists(self.device) else None

        persistent_candidates = [
            "/dev/input/by-path/platform-pcspkr-event-spkr",
        ]

        for path in persistent_candidates:
            if os.path.exists(path):
                return path

        for path in sorted(glob.glob("/dev/input/event*")):
            if self._device_name(path).lower() == "pc speaker":
                return path

        return None

    def available(self):
        if not self.enabled:
            return False

        if self.backend == "pcspkr":
            return self.find_device() is not None

        if self.backend == "terminal":
            return True

        return False

    @staticmethod
    def _event(frequency):
        return struct.pack(
            "llHHi",
            0,
            0,
            EV_SND,
            SND_TONE,
            int(frequency),
        )

    def _tone(self, frequency, duration):
        device = self.find_device()

        if device is None:
            LOGGER.warning("Linux PC-speaker device was not found")
            return False

        try:
            with open(device, "wb", buffering=0) as speaker:
                speaker.write(self._event(frequency))
                time.sleep(duration)
                speaker.write(self._event(0))
        except OSError as error:
            LOGGER.warning(
                "Unable to use PC speaker %s: %s",
                device,
                error,
            )
            return False

        return True

    def beep(self, pattern="short", force=False):
        if not self.enabled:
            return False

        now = time.monotonic()

        with self.lock:
            if not force and now - self.last_beep < self.cooldown:
                return False

            if self.backend == "pcspkr":
                if pattern == "long":
                    success = self._tone(
                        self.long_frequency,
                        self.long_duration,
                    )
                else:
                    success = self._tone(
                        self.short_frequency,
                        self.short_duration,
                    )
            elif self.backend == "terminal":
                print("\a", end="", flush=True)
                success = True
            else:
                LOGGER.warning(
                    "Unsupported buzzer backend: %s",
                    self.backend,
                )
                success = False

            if success:
                self.last_beep = now

            return success

    def startup(self):
        return self.beep(
            self.config.get("startup", "long"),
            force=True,
        )

    def shutdown(self):
        return self.beep(
            self.config.get("shutdown", "short"),
            force=True,
        )

    def alert(self, priority):
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 70

        pattern = (
            self.config.get("critical", "long")
            if priority >= 100
            else self.config.get("warning", "short")
        )

        return self.beep(pattern)
