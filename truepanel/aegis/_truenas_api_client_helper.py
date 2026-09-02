"""Host-Python bridge for TrueNAS's appliance-owned API client.

This helper intentionally uses only the standard library until it imports the
TrueNAS-provided ``truenas_api_client`` package. It speaks a tiny line-delimited
JSON protocol over stdin/stdout and exposes only authentication plus the same
passive evidence methods allowed by the parent AEGIS runtime.
"""

from __future__ import annotations

import json
import sys
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

PASSIVE_METHODS = {
    "auth.me",
    "cloud_backup.query",
    "disk.query",
    "replication.query",
}
ALLOWED_CALL_METHODS = PASSIVE_METHODS | {"auth.login_ex"}


def _emit(payload: dict[str, Any]) -> None:
    def default(value: Any) -> Any:
        if isinstance(value, (set, frozenset)):
            return sorted(value)
        raise TypeError

    try:
        encoded = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
            default=default,
        )
    except Exception:
        encoded = '{"ok":false}'
    sys.stdout.write(encoded + "\n")
    sys.stdout.flush()


def _valid_open_request(request: dict[str, Any]) -> tuple[str, float] | None:
    uri = request.get("uri")
    verify_ssl = request.get("verify_ssl")
    call_timeout = request.get("call_timeout")
    if not isinstance(uri, str) or verify_ssl is not True:
        return None
    parsed = urlsplit(uri)
    if (
        parsed.scheme != "wss"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path != "/api/current"
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        timeout = float(call_timeout)
    except (TypeError, ValueError):
        return None
    if not 1 <= timeout <= 30:
        return None
    return uri, timeout


def main() -> int:
    try:
        from truenas_api_client import Client
    except Exception:
        _emit({"ok": False})
        return 1

    client: Any | None = None
    authenticated = False
    try:
        for raw_line in sys.stdin:
            try:
                request = json.loads(raw_line)
            except Exception:
                _emit({"ok": False})
                continue
            if not isinstance(request, dict):
                _emit({"ok": False})
                continue

            operation = request.get("op")
            if operation == "open":
                if client is not None:
                    _emit({"ok": False})
                    continue
                validated = _valid_open_request(request)
                if validated is None:
                    _emit({"ok": False})
                    continue
                uri, call_timeout = validated
                try:
                    client = Client(
                        uri=uri,
                        verify_ssl=True,
                        call_timeout=call_timeout,
                    )
                except Exception:
                    client = None
                    _emit({"ok": False})
                    continue
                _emit({"ok": True})
                continue

            if operation == "call":
                method = request.get("method")
                arguments = request.get("arguments")
                if (
                    client is None
                    or method not in ALLOWED_CALL_METHODS
                    or not isinstance(arguments, list)
                ):
                    _emit({"ok": False})
                    continue
                if method == "auth.login_ex":
                    if authenticated:
                        _emit({"ok": False})
                        continue
                elif not authenticated:
                    _emit({"ok": False})
                    continue
                try:
                    result = client.call(method, *arguments)
                except Exception:
                    _emit({"ok": False})
                    continue
                if (
                    method == "auth.login_ex"
                    and isinstance(result, dict)
                    and result.get("response_type") == "SUCCESS"
                ):
                    authenticated = True
                _emit({"ok": True, "result": result})
                continue

            if operation == "close":
                _emit({"ok": True})
                return 0

            _emit({"ok": False})
    finally:
        if client is not None:
            with suppress(Exception):
                client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
