"""
Guarded hardware executor for TruePanel fan-control decisions.

The executor performs the smallest possible sysfs write surface. Policy belongs
in fan_control.py; this module only applies an already validated decision and
restores motherboard automatic control after failures or shutdown.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from truepanel.hardware.fan_control import (
    FanControlDecision,
    FanProfile,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FanChannelSnapshot:
    number: int
    pwm: int
    mode: int


class FanHardwareExecutor:
    """
    Apply validated decisions to bounded Fintek PWM channels.

    Only explicitly configured channels are touched. Automatic mode is the
    fail-safe destination after errors and when the executor is closed.
    """

    AUTO_MODE = 2
    MANUAL_MODE = 1

    def __init__(
        self,
        base: str | Path,
        *,
        controlled_channels: Sequence[int] = (1, 2),
        reader: Callable[[Path], int] | None = None,
        writer: Callable[[Path, int], None] | None = None,
    ):
        self.base = Path(base)
        self.controlled_channels = self._normalize_channels(
            controlled_channels
        )
        self.reader = reader or self._default_reader
        self.writer = writer or self._default_writer
        self._closed = False
        self._snapshots: dict[
            int,
            FanChannelSnapshot,
        ] = {}

        self._validate_surface()
        self._capture_original_state()

    @staticmethod
    def _normalize_channels(
        channels: Sequence[int],
    ) -> tuple[int, ...]:
        normalized = tuple(
            int(channel)
            for channel in channels
        )

        if not normalized:
            raise ValueError(
                "At least one controlled fan channel is required."
            )

        if len(set(normalized)) != len(normalized):
            raise ValueError(
                "Controlled fan channels must be unique."
            )

        for channel in normalized:
            if channel not in (1, 2):
                raise ValueError(
                    "Only verified fan channels 1 and 2 "
                    "may be controlled."
                )

        return normalized

    @staticmethod
    def _default_reader(
        path: Path,
    ) -> int:
        return int(
            path.read_text().strip()
        )

    @staticmethod
    def _default_writer(
        path: Path,
        value: int,
    ) -> None:
        path.write_text(
            str(int(value))
        )

    def _pwm_path(
        self,
        channel: int,
    ) -> Path:
        return self.base / f"pwm{channel}"

    def _mode_path(
        self,
        channel: int,
    ) -> Path:
        return self.base / f"pwm{channel}_enable"

    def _validate_surface(self) -> None:
        if not self.base.exists():
            raise RuntimeError(
                f"Fan controller path does not exist: {self.base}"
            )

        for channel in self.controlled_channels:
            for path in (
                self._pwm_path(channel),
                self._mode_path(channel),
            ):
                if not path.exists():
                    raise RuntimeError(
                        f"Required fan-control attribute is missing: "
                        f"{path}"
                    )

    def _capture_original_state(self) -> None:
        for channel in self.controlled_channels:
            snapshot = FanChannelSnapshot(
                number=channel,
                pwm=self.reader(
                    self._pwm_path(channel)
                ),
                mode=self.reader(
                    self._mode_path(channel)
                ),
            )

            self._snapshots[
                channel
            ] = snapshot

        LOGGER.info(
            "Captured original fan-control state: %s",
            self.snapshot(),
        )

    def snapshot(
        self,
    ) -> Mapping[int, FanChannelSnapshot]:
        return dict(
            self._snapshots
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError(
                "Fan hardware executor is closed."
            )

    def restore_automatic(self) -> None:
        """
        Return every controlled channel to motherboard automatic mode.

        Each channel is attempted independently so one failed write does not
        prevent restoration attempts on the remaining channel.
        """

        errors = []

        for channel in self.controlled_channels:
            path = self._mode_path(
                channel
            )

            try:
                self.writer(
                    path,
                    self.AUTO_MODE,
                )
            except Exception as error:
                errors.append(
                    (
                        channel,
                        error,
                    )
                )

                LOGGER.exception(
                    "Could not restore Fan %d to automatic mode",
                    channel,
                )

        if errors:
            failed = ", ".join(
                str(channel)
                for channel, _ in errors
            )

            raise RuntimeError(
                "Could not restore automatic mode for "
                f"fan channel(s): {failed}"
            )

        LOGGER.info(
            "Restored controlled fan channels to automatic mode"
        )

    def _apply_manual_pwm(
        self,
        pwm: int,
    ) -> None:
        pwm = max(
            0,
            min(
                255,
                int(pwm),
            ),
        )

        try:
            # Stage the requested PWM while automatic control is still active.
            for channel in self.controlled_channels:
                self.writer(
                    self._pwm_path(
                        channel
                    ),
                    pwm,
                )

            # Enter manual mode only after every PWM value is staged.
            for channel in self.controlled_channels:
                self.writer(
                    self._mode_path(
                        channel
                    ),
                    self.MANUAL_MODE,
                )
        except Exception:
            LOGGER.exception(
                "Fan-control write failed; restoring automatic mode"
            )

            try:
                self.restore_automatic()
            except Exception:
                LOGGER.exception(
                    "Automatic rollback also encountered an error"
                )

            raise

        LOGGER.info(
            "Applied manual PWM %d to fan channels %s",
            pwm,
            self.controlled_channels,
        )

    def apply(
        self,
        decision: FanControlDecision,
    ) -> None:
        self._ensure_open()

        if decision.force_automatic:
            self.restore_automatic()
            return

        if (
            decision.effective_profile
            is FanProfile.AFTERBURNERS
        ):
            self._apply_manual_pwm(
                255
            )
            return

        if not decision.accepted:
            raise ValueError(
                "Rejected fan-control decision cannot be applied."
            )

        if decision.pwm is None:
            raise ValueError(
                "Manual fan-control decision does not include PWM."
            )

        self._apply_manual_pwm(
            decision.pwm
        )

    def close(self) -> None:
        if self._closed:
            return

        try:
            self.restore_automatic()
        finally:
            self._closed = True

    def __enter__(
        self,
    ):
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.close()
        return False


__all__ = [
    "FanChannelSnapshot",
    "FanHardwareExecutor",
]
