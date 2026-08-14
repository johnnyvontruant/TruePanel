"""Offline Mission Control adapter for Black Box replay data.

The adapter deliberately stops at route-shaped request/response objects. It
does not import or attach to TruePanel's live web server, open sockets, invoke
callbacks, or acquire any hardware/service authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

from truepanel.history.black_box_api import BlackBoxReplayAPI


BLACK_BOX_REPLAY_ROUTE_SCHEMA_VERSION = 1
REPLAY_ROUTE_PREFIX = "/api/v1/replay"
MAX_QUERY_FIELDS = 8
MAX_QUERY_VALUE_LENGTH = 64


@dataclass(frozen=True)
class ReplayRouteRequest:
    """A minimal transport-neutral request shape for offline replay."""

    method: str
    target: str

    def __post_init__(self) -> None:
        method = str(self.method).upper()
        target = str(self.target)
        if not target.startswith("/"):
            raise ValueError("replay route target must be an absolute path")
        if len(target) > 2048:
            raise ValueError("replay route target is too long")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "target", target)


@dataclass(frozen=True)
class ReplayRouteResponse:
    """A JSON-serializable response shape without a network transport."""

    status: int
    body: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BLACK_BOX_REPLAY_ROUTE_SCHEMA_VERSION,
            "status": int(self.status),
            "body": dict(self.body),
        }


def _error(status: int, code: str, message: str) -> ReplayRouteResponse:
    return ReplayRouteResponse(
        status=status,
        body={
            "schema_version": BLACK_BOX_REPLAY_ROUTE_SCHEMA_VERSION,
            "read_only": True,
            "error": {
                "code": code,
                "message": message,
            },
        },
    )


def _parse_query(query: str) -> dict[str, str]:
    parsed = parse_qs(
        query,
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=MAX_QUERY_FIELDS,
    )
    normalized: dict[str, str] = {}
    for key, values in parsed.items():
        if len(values) != 1:
            raise ValueError(f"query field must appear once: {key}")
        value = values[0]
        if len(key) > MAX_QUERY_VALUE_LENGTH or len(value) > MAX_QUERY_VALUE_LENGTH:
            raise ValueError("replay route query field is too long")
        normalized[key] = value
    return normalized


def _reject_unknown_query(
    query: Mapping[str, str],
    *,
    allowed: frozenset[str],
) -> None:
    unknown = sorted(set(query) - allowed)
    if unknown:
        raise ValueError(f"unsupported query field: {unknown[0]}")


def _optional_int(query: Mapping[str, str], name: str) -> int | None:
    value = query.get(name)
    return None if value is None else int(value)


class BlackBoxMissionControlReplayAdapter:
    """Map an offline replay API to route-shaped read-only responses."""

    def __init__(self, api: BlackBoxReplayAPI):
        if not isinstance(api, BlackBoxReplayAPI):
            raise TypeError("adapter requires BlackBoxReplayAPI")
        self.api = api

    def handle(self, request: ReplayRouteRequest) -> ReplayRouteResponse:
        if not isinstance(request, ReplayRouteRequest):
            raise TypeError("request must be ReplayRouteRequest")

        if request.method != "GET":
            return _error(
                405,
                "method_not_allowed",
                "offline replay routes are read-only GET operations",
            )

        parts = urlsplit(request.target)
        if parts.scheme or parts.netloc or parts.fragment:
            return _error(
                400,
                "invalid_target",
                "replay route target must be a local path and query",
            )

        try:
            query = _parse_query(parts.query)
            return self._dispatch(parts.path, query)
        except (TypeError, ValueError, OverflowError) as exc:
            return _error(400, "invalid_request", str(exc))

    def _dispatch(
        self,
        path: str,
        query: Mapping[str, str],
    ) -> ReplayRouteResponse:
        if path in {REPLAY_ROUTE_PREFIX, f"{REPLAY_ROUTE_PREFIX}/"}:
            _reject_unknown_query(query, allowed=frozenset())
            return ReplayRouteResponse(200, self.api.metadata())

        if path == f"{REPLAY_ROUTE_PREFIX}/seek":
            _reject_unknown_query(query, allowed=frozenset({"captured_at"}))
            if "captured_at" not in query:
                raise ValueError("captured_at is required")
            payload = self.api.seek(float(query["captured_at"]))
            if payload is None:
                return _error(404, "frame_not_found", "no frame at or before timestamp")
            return ReplayRouteResponse(200, payload)

        if path == f"{REPLAY_ROUTE_PREFIX}/timeline":
            _reject_unknown_query(
                query,
                allowed=frozenset({"start_sequence", "end_sequence", "limit"}),
            )
            payload = self.api.timeline(
                start_sequence=_optional_int(query, "start_sequence"),
                end_sequence=_optional_int(query, "end_sequence"),
                limit=int(query.get("limit", "256")),
            )
            return ReplayRouteResponse(200, payload)

        if path == f"{REPLAY_ROUTE_PREFIX}/incidents":
            _reject_unknown_query(query, allowed=frozenset({"limit"}))
            payload = self.api.incident_history(
                limit=int(query.get("limit", "256")),
            )
            return ReplayRouteResponse(200, payload)

        if path == f"{REPLAY_ROUTE_PREFIX}/chaos":
            _reject_unknown_query(query, allowed=frozenset())
            return ReplayRouteResponse(200, self.api.scenario_contract())

        frame_prefix = f"{REPLAY_ROUTE_PREFIX}/frame/"
        if path.startswith(frame_prefix):
            _reject_unknown_query(query, allowed=frozenset())
            sequence_text = path[len(frame_prefix):]
            if not sequence_text or "/" in sequence_text:
                return _error(404, "route_not_found", "replay route not found")
            payload = self.api.frame(int(sequence_text))
            if payload is None:
                return _error(404, "frame_not_found", "replay frame not found")
            return ReplayRouteResponse(200, payload)

        return _error(404, "route_not_found", "replay route not found")


__all__ = [
    "BLACK_BOX_REPLAY_ROUTE_SCHEMA_VERSION",
    "MAX_QUERY_FIELDS",
    "MAX_QUERY_VALUE_LENGTH",
    "REPLAY_ROUTE_PREFIX",
    "BlackBoxMissionControlReplayAdapter",
    "ReplayRouteRequest",
    "ReplayRouteResponse",
]
