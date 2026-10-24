"""Local channels between the Loadmaster service, the LCD and Mission Control.

* Status: the service rewrites ``loadmaster-status.json`` atomically on every
  change and about once a second while copying.
* Commands: a Unix socket accepting one JSON request per connection:

  ``{"action": "start", "digest": "...", "confirm": true, "source": "web"}``
  ``{"action": "stop" | "eject" | "rescan" | "adopt", "source": "web" | "lcd"}``

Neither channel imports hardware code, so Mission Control stays unprivileged.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from .state import write_json_atomic

LOGGER = logging.getLogger(__name__)

STATUS_PATH = Path("/run/truepanel/loadmaster-status.json")
COMMAND_SOCKET = Path("/run/truepanel/loadmaster-command.sock")
ACTIONS = frozenset({"start", "stop", "eject", "rescan", "adopt"})
SOURCES = frozenset({"web", "lcd", "host"})
STALE_AFTER = 30.0
MAX_REQUEST = 4096


def publish_status(path: Path, status: dict[str, Any]) -> None:
    write_json_atomic(path, {"published": time.time(), "status": status})


def read_status(
    path: Path, *, clock: Callable[[], float] = time.time
) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        status = dict(document["status"])
        age = clock() - float(document["published"])
    except FileNotFoundError:
        return {
            "available": False,
            "state": "OFF",
            "message": "Loadmaster is not running or not enabled.",
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {
            "available": False,
            "state": "OFF",
            "message": "Loadmaster status could not be read.",
        }
    status["age"] = round(age, 1)
    status["available"] = age <= STALE_AFTER
    if not status["available"]:
        status["message"] = "Loadmaster has stopped reporting; is TruePanel running?"
    return status


def reply(ok: bool, status: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": ok, "status": status, "message": message, **extra}


def validate(request: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (clean request, None) or (None, error reply)."""

    if not isinstance(request, dict):
        return None, reply(False, "invalid", "request must be a JSON object")
    extra = set(request) - {"action", "source", "digest", "confirm"}
    if extra:
        return None, reply(
            False, "invalid", f"unknown fields: {', '.join(sorted(extra))}"
        )
    action = str(request.get("action") or "")
    source = str(request.get("source") or "")
    if action not in ACTIONS:
        return None, reply(
            False, "invalid", "action must be start, stop, eject, rescan or adopt"
        )
    if source not in SOURCES:
        return None, reply(False, "invalid", "source must be web or lcd")
    clean = {"action": action, "source": source}
    if action == "start":
        digest = request.get("digest")
        if not isinstance(digest, str) or len(digest) != 64:
            return None, reply(False, "invalid", "start needs the plan digest")
        if request.get("confirm") is not True:
            return None, reply(
                False, "confirmation_required", "start must be confirmed"
            )
        clean["digest"] = digest
        clean["confirm"] = True
    return clean, None


class CommandServer:
    def __init__(self, path: Path, handler: Callable[[dict[str, Any]], dict[str, Any]]):
        self.path = path
        self.handler = handler
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with suppress(FileNotFoundError):
            self.path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.path))
        os.chmod(self.path, 0o660)
        sock.listen(8)
        sock.settimeout(0.5)
        self._sock = sock
        self._thread = threading.Thread(
            target=self._serve, name="loadmaster-commands", daemon=True
        )
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(5)
            try:
                data = b""
                while b"\n" not in data and len(data) <= MAX_REQUEST:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                request = json.loads(data.split(b"\n", 1)[0] or b"null")
                clean, error = validate(request)
                if error is not None:
                    answer = error
                elif clean["action"] == "start" and clean["source"] == "host":
                    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                    _pid, uid, _gid = struct.unpack("3i", raw)
                    if uid != 0:
                        answer = reply(False, "unauthorized", "Host authorization required.")
                    else:
                        clean["_host_authenticated"] = True
                        answer = self.handler(clean)
                else:
                    answer = self.handler(clean)
            except (OSError, ValueError) as exc:
                answer = reply(False, "invalid", str(exc))
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Loadmaster command failed")
                answer = reply(False, "error", str(exc))
            with suppress(OSError):
                conn.sendall(json.dumps(answer).encode() + b"\n")

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            with suppress(OSError):
                self._sock.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        with suppress(FileNotFoundError):
            self.path.unlink()


class LinkError(RuntimeError):
    pass


def send_command(path: Path, request: dict[str, Any], *, timeout: float = 30.0) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(path))
        sock.sendall(json.dumps(request).encode() + b"\n")
        data = b""
        while chunk := sock.recv(4096):
            data += chunk
            if b"\n" in data:
                break
    except OSError as error:
        raise LinkError(f"Loadmaster is not reachable: {error}") from error
    finally:
        sock.close()
    try:
        answer = json.loads(data.split(b"\n", 1)[0])
    except ValueError as error:
        raise LinkError("Loadmaster sent an unreadable reply") from error
    if not isinstance(answer, dict):
        raise LinkError("Loadmaster sent an unreadable reply")
    return answer


__all__ = [
    "CommandServer",
    "LinkError",
    "publish_status",
    "read_status",
    "reply",
    "send_command",
    "validate",
]
