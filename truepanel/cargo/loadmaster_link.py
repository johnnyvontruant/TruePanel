"""Status file and command socket shared by the LCD and Mission Control.

The Loadmaster controller lives in the process that owns the Host runtime
(today the LCD service). Two small local channels let other surfaces see and
steer it without importing any hardware code:

* **Status** — the controller atomically rewrites
  ``/run/truepanel/loadmaster-status.json`` on every state change and about
  once a second while copying. The LCD screens and Mission Control both read it.
* **Commands** — a Unix socket at ``/run/truepanel/loadmaster-command.sock``
  accepts exactly three actions:

  ``start``   begin a READY run. Requires the plan digest the operator was
              shown and the confirmation phrase; refused unless remote
              confirmation is enabled in configuration.
  ``eject``   flush and unmount the docked cartridge without transferring.
  ``refresh`` re-plan now (also re-arms a cartridge that already ran).

Every request is one JSON object per connection, newline terminated, and every
response says whether it was accepted and why not.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

DEFAULT_LOADMASTER_STATUS_PATH = Path("/run/truepanel/loadmaster-status.json")
DEFAULT_LOADMASTER_COMMAND_SOCKET = Path("/run/truepanel/loadmaster-command.sock")
LOADMASTER_STATUS_KIND = "truepanel.loadmaster_status"
START_CONFIRMATION = "START_LOADMASTER_TRANSFER"
ALLOWED_SOURCES = frozenset({"web", "lcd"})
ALLOWED_ACTIONS = frozenset({"start", "eject", "refresh"})
MAX_REQUEST_BYTES = 2048
DEFAULT_STATUS_MAX_AGE = 30.0


class LoadmasterLinkError(RuntimeError):
    """The Loadmaster command channel is unreachable or replied badly."""


# ------------------------------------------------------------------- status


def publish_status(
    payload: Mapping[str, Any],
    path: Path = DEFAULT_LOADMASTER_STATUS_PATH,
) -> None:
    document = {
        "schema_version": 1,
        "kind": LOADMASTER_STATUS_KIND,
        "published_at": time.time(),
        "status": dict(payload),
    }
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True, default=str)
        os.chmod(name, 0o644)
        os.replace(name, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(name)
        raise


def read_status(
    path: Path = DEFAULT_LOADMASTER_STATUS_PATH,
    *,
    max_age: float = DEFAULT_STATUS_MAX_AGE,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Return the latest status, or an UNAVAILABLE placeholder.

    A status file older than ``max_age`` means the owning process stopped; it
    is reported as stale rather than trusted.
    """

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _unavailable("Loadmaster is not running (execution disabled?)")
    except (OSError, json.JSONDecodeError) as error:
        return _unavailable(f"Loadmaster status unreadable: {error}")

    if (
        not isinstance(document, dict)
        or document.get("kind") != LOADMASTER_STATUS_KIND
        or not isinstance(document.get("status"), dict)
    ):
        return _unavailable("Loadmaster status is malformed")

    published = float(document.get("published_at") or 0)
    status = dict(document["status"])
    age = max(0.0, clock() - published)
    status["age_seconds"] = round(age, 1)
    status["stale"] = age > max_age
    if status["stale"]:
        status["available"] = False
        status["reason"] = "Loadmaster status is stale; is TruePanel running?"
    else:
        status["available"] = True
    return status


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "stale": False,
        "state": "UNAVAILABLE",
        "reason": reason,
        "cartridge": None,
        "plan": None,
        "progress": None,
        "last_receipt": None,
        "unregistered": [],
        "remote_start_enabled": False,
    }


# ---------------------------------------------------------------- commands


def _response(ok: bool, status: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": bool(ok), "status": status, "message": message, **extra}


class LoadmasterCommandProcessor:
    """Validate one request and route it to the controller."""

    def __init__(self, controller: Any) -> None:
        self.controller = controller

    def process(self, request: Any) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            return _response(False, "invalid_request", "Request must be an object.")

        unknown = sorted(
            set(request) - {"action", "source", "plan_digest", "confirmation"}
        )
        if unknown:
            return _response(
                False, "invalid_request", "Unknown fields: " + ", ".join(unknown)
            )

        action = str(request.get("action") or "").strip().lower()
        source = str(request.get("source") or "").strip().lower()

        if action not in ALLOWED_ACTIONS:
            return _response(
                False,
                "unknown_action",
                "action must be start, eject, or refresh.",
                allowed_actions=sorted(ALLOWED_ACTIONS),
            )
        if source not in ALLOWED_SOURCES:
            return _response(False, "invalid_source", "source must be web or lcd.")

        try:
            if action == "eject":
                return self.controller.request_eject(source=source)
            if action == "refresh":
                return self.controller.request_refresh(source=source)

            digest = request.get("plan_digest")
            if not isinstance(digest, str) or len(digest) != 64:
                return _response(
                    False, "invalid_request", "start requires the plan digest."
                )
            if request.get("confirmation") != START_CONFIRMATION:
                return _response(
                    False,
                    "confirmation_required",
                    "start requires explicit confirmation.",
                    confirmation_required=START_CONFIRMATION,
                )
            return self.controller.request_start(plan_digest=digest, source=source)
        except Exception as error:  # noqa: BLE001 - always answer the caller
            LOGGER.exception("Loadmaster command failed")
            return _response(False, "execution_failed", str(error))


class LoadmasterCommandServer:
    """Unix-socket server owned by the process that owns the controller."""

    def __init__(
        self,
        processor: LoadmasterCommandProcessor,
        path: Path = DEFAULT_LOADMASTER_COMMAND_SOCKET,
    ) -> None:
        self.processor = processor
        self.path = Path(path)
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        with suppress(FileNotFoundError):
            self.path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.path))
        os.chmod(self.path, 0o660)
        server.listen(4)
        server.settimeout(0.25)
        self._socket = server
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._serve, name="truepanel-loadmaster-command", daemon=True
        )
        self._thread.start()

    def _serve(self) -> None:
        assert self._socket is not None
        while not self._stop.is_set():
            try:
                connection, _ = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                raise
            # Commands can take a few seconds (refresh re-plans); handle each
            # connection on its own thread so a slow one cannot block accept.
            threading.Thread(
                target=self._handle, args=(connection,), daemon=True
            ).start()

    def _handle(self, connection: socket.socket) -> None:
        with connection:
            connection.settimeout(5.0)
            try:
                raw = _read_line(connection)
                request = json.loads(raw.decode("utf-8"))
                response = self.processor.process(request)
            except ValueError as error:
                response = _response(False, "invalid_json", str(error))
            except OSError as error:
                response = _response(False, "invalid_request", str(error))
            with suppress(OSError):
                connection.sendall(
                    json.dumps(response, sort_keys=True).encode("utf-8") + b"\n"
                )

    def stop(self) -> None:
        self._stop.set()
        if self._socket is not None:
            with suppress(OSError):
                self._socket.close()
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        with suppress(FileNotFoundError):
            self.path.unlink()


def _read_line(connection: socket.socket) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= MAX_REQUEST_BYTES:
        chunk = connection.recv(1024)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk:
            break
    if total > MAX_REQUEST_BYTES:
        raise ValueError("request too large")
    return b"".join(chunks).split(b"\n", 1)[0]


class LoadmasterCommandClient:
    """Client for Mission Control and the LCD; no hardware imports."""

    def __init__(
        self,
        path: Path = DEFAULT_LOADMASTER_COMMAND_SOCKET,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.path = Path(path)
        self.timeout = float(timeout)

    def request(self, action: str, *, source: str, **fields: Any) -> dict[str, Any]:
        payload = {"action": action, "source": source, **fields}
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(self.timeout)
        try:
            client.connect(str(self.path))
            client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            client.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError as error:
            raise LoadmasterLinkError(
                f"Loadmaster command socket is unavailable: {error}"
            ) from error
        finally:
            client.close()
        try:
            response = json.loads(b"".join(chunks).split(b"\n", 1)[0])
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LoadmasterLinkError("Loadmaster reply was not JSON") from error
        if not isinstance(response, dict):
            raise LoadmasterLinkError("Loadmaster reply was not an object")
        return response


__all__ = [
    "ALLOWED_ACTIONS",
    "DEFAULT_LOADMASTER_COMMAND_SOCKET",
    "DEFAULT_LOADMASTER_STATUS_PATH",
    "LoadmasterCommandClient",
    "LoadmasterCommandProcessor",
    "LoadmasterCommandServer",
    "LoadmasterLinkError",
    "START_CONFIRMATION",
    "publish_status",
    "read_status",
]
