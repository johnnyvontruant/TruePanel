"""In-process, one-use freshness gate for WINGMAN's experimental HOLD view.

This is a lab-only component, NOT an authentication mechanism for code running
inside the TruePanel process. The future server integration must inject only
its trusted internal status composer, never a client payload, cached response,
saved HoloDeck fixture, or retrieved document. No production route uses it.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from copy import deepcopy
from threading import Lock
from typing import Any

from .hold_envelope import project_operator_view
from .hold_snapshot_adapter import holds_from_trusted_snapshot
from .service import WingmanServiceResult


def _unavailable(reason: str) -> dict[str, Any]:
    """No model text or authority when a trusted status decision cannot be made."""
    return {
        "schema_version": 1,
        "project": "WINGMAN",
        "status": "EVIDENCE_UNAVAILABLE",
        "authoritative_holds": [],
        "operator_notice": (
            "Current authoritative HOLD status is unavailable. "
            "Do not interpret missing evidence as permission for physical service "
            "or an AEGIS override. Check TruePanel's authoritative status."
        ),
        "generated_explanation": None,
        "generated_explanation_suppressed": True,
        "suppression_reason": reason,
        "control_authority": False,
        "production_mutation": False,
        "hold_release_authorized": False,
        "evidence_origin": "UNVERIFIED",
        "advisory_only": True,
    }


class TrustedSnapshotGate:
    """Accept snapshots only through a pre-wired internal composer.

    The opaque ticket can be redeemed once on the same gate instance within
    max_age_seconds. A newer capture invalidates earlier tickets. Monotonic
    clock movement backwards, stale tickets, reused tickets, foreign objects,
    malformed authoritative fields and composition failures all fail closed.
    """

    def __init__(
        self,
        *,
        composer: Callable[[], dict[str, Any]],
        max_age_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not callable(composer) or not callable(clock):
            raise ValueError("Internal composer and monotonic clock are required")
        if (
            not isinstance(max_age_seconds, (int, float))
            or isinstance(max_age_seconds, bool)
            or not math.isfinite(max_age_seconds)
            or not 0 < max_age_seconds <= 30
        ):
            raise ValueError("HOLD snapshot TTL must be between 0 and 30 seconds")
        self._composer = composer
        self._clock = clock
        self._lock = Lock()
        self._max_age = float(max_age_seconds)
        self._ticket: object | None = None
        self._snapshot: dict[str, Any] | None = None
        self._captured_at: float | None = None

    def capture(self) -> object:
        """Mint one non-serializable ticket from the internal composer only."""
        with self._lock:
            return self._capture_locked()

    def _capture_locked(self) -> object:
        self._ticket = None
        self._snapshot = None
        self._captured_at = None
        try:
            snapshot = self._composer()
            if not isinstance(snapshot, dict):
                raise ValueError("Internal composer did not return a snapshot")
            isolated = deepcopy(snapshot)
            captured_at = float(self._clock())
            if not math.isfinite(captured_at):
                raise ValueError("Monotonic clock unavailable")
        except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError):
            # An unsuccessful capture cannot mint authority.
            return object()

        ticket = object()
        self._ticket = ticket
        self._snapshot = isolated
        self._captured_at = captured_at
        return ticket

    def project(
        self,
        result: WingmanServiceResult,
        *,
        ticket: object,
    ) -> dict[str, Any]:
        """Consume the ticket and produce a HOLD-aware view, or fail closed."""
        with self._lock:
            return self._project_locked(result, ticket=ticket)

    def _project_locked(
        self, result: WingmanServiceResult, *, ticket: object
    ) -> dict[str, Any]:
        if ticket is not self._ticket or self._snapshot is None:
            return _unavailable("UNTRUSTED_OR_REPLAYED_SNAPSHOT")
        snapshot = self._snapshot
        captured_at = self._captured_at
        # Even a failed redemption spends the ticket. Do not permit retries
        # after a status change, elapsed TTL, or mutated model response.
        self._ticket = None
        self._snapshot = None
        self._captured_at = None
        try:
            now = float(self._clock())
            if (
                not math.isfinite(now)
                or captured_at is None
                or now < captured_at
                or now - captured_at > self._max_age
            ):
                return _unavailable("STALE_SNAPSHOT")
            holds = holds_from_trusted_snapshot(snapshot)
            return project_operator_view(result, trusted_holds=holds)
        except (TypeError, ValueError, KeyError, AttributeError):
            return _unavailable("INVALID_AUTHORITATIVE_EVIDENCE")


__all__ = ["TrustedSnapshotGate"]
