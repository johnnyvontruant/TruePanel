"""
One-time authorization for live protocol experiments.
"""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from uuid import uuid4


PROTOCOL_ARMING_PHRASE = (
    "STARGATE PROTOCOL DISPLAY EXPERIMENT"
)


@dataclass
class ProtocolAuthorization:
    experiment_id: str
    token: str
    issued_at: float
    expires_at: float
    consumed: bool = False

    @classmethod
    def issue(
        cls,
        experiment_id,
        phrase,
        *,
        lifetime_seconds=120.0,
        clock=time.monotonic,
    ):
        if not experiment_id:
            raise ValueError(
                "experiment_id is required"
            )

        if not hmac.compare_digest(
            str(phrase),
            PROTOCOL_ARMING_PHRASE,
        ):
            raise PermissionError(
                "Exact protocol arming phrase is required"
            )

        if lifetime_seconds <= 0:
            raise ValueError(
                "lifetime_seconds must be positive"
            )

        now = float(clock())

        return cls(
            experiment_id=experiment_id,
            token=uuid4().hex,
            issued_at=now,
            expires_at=now + float(lifetime_seconds),
        )

    def is_valid_for(
        self,
        experiment_id,
        *,
        clock=time.monotonic,
    ):
        return (
            not self.consumed
            and self.experiment_id == experiment_id
            and float(clock()) <= self.expires_at
        )

    def consume(
        self,
        experiment_id,
        *,
        clock=time.monotonic,
    ):
        if not self.is_valid_for(
            experiment_id,
            clock=clock,
        ):
            raise PermissionError(
                "Protocol authorization is invalid, expired, "
                "consumed, or belongs to another experiment"
            )

        self.consumed = True
        return True

    def as_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "token": self.token,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "consumed": self.consumed,
        }
