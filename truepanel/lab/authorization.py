"""
Laboratory execution authorization.

Authorization is deliberately separate from the interlock policy. An
authorization proves that a caller deliberately approved a specific request;
it does not guarantee that the request is safe.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_hex


@dataclass(frozen=True)
class ExecutionAuthorization:
    request_id: str
    token: str
    issued_at: datetime
    expires_at: datetime
    operator: str = "unknown"

    @classmethod
    def issue(
        cls,
        request_id,
        *,
        operator="unknown",
        lifetime_seconds=60,
        now=None,
    ):
        if not request_id:
            raise ValueError("request_id is required")

        if lifetime_seconds <= 0:
            raise ValueError(
                "lifetime_seconds must be greater than zero"
            )

        issued_at = now or datetime.now(UTC)

        return cls(
            request_id=request_id,
            token=token_hex(16),
            issued_at=issued_at,
            expires_at=issued_at
            + timedelta(seconds=lifetime_seconds),
            operator=operator,
        )

    def is_valid_for(self, request_id, *, now=None):
        current_time = now or datetime.now(UTC)

        return (
            bool(self.token)
            and self.request_id == request_id
            and self.issued_at <= current_time
            and current_time < self.expires_at
        )
