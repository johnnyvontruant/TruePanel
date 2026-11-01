"""Guarded local command channel for virtual LCD button presses."""

from __future__ import annotations

import json
import logging
import socket
import threading
from pathlib import Path
from typing import Any, Callable, Mapping


LOGGER = logging.getLogger(__name__)

DEFAULT_LCD_COMMAND_SOCKET_PATH = Path(
    "/run/truepanel/lcd-command.sock"
)
DEFAULT_LCD_COMMAND_TIMEOUT = 3.0
MAX_REQUEST_BYTES = 1024

LCD_BUTTON_MASKS = {
    "enter": 0x01,
    "select": 0x02,
}


class LCDCommandError(RuntimeError):
    """Raised when the LCD command runtime cannot be reached."""


def _response(
    *,
    ok: bool,
    status: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "status": str(status),
        "message": str(message),
        **extra,
    }


class LCDCommandProcessor:
    """Validate web button requests and submit them to the LCD dispatcher."""

    def __init__(
        self,
        submit_button: Callable[[int, str], bool],
    ):
        self.submit_button = submit_button

    def process(
        self,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(
            request,
            Mapping,
        ):
            return _response(
                ok=False,
                status="invalid_request",
                message="LCD command must be a JSON object.",
            )

        unknown_fields = sorted(
            set(request)
            - {
                "button",
                "source",
            }
        )

        if unknown_fields:
            return _response(
                ok=False,
                status="invalid_request",
                message=(
                    "Unknown LCD command fields: "
                    + ", ".join(unknown_fields)
                ),
            )

        button = request.get(
            "button"
        )

        if not isinstance(
            button,
            str,
        ):
            return _response(
                ok=False,
                status="invalid_request",
                message="button must be a string.",
            )

        button = button.strip().lower()

        if button not in LCD_BUTTON_MASKS:
            return _response(
                ok=False,
                status="unknown_button",
                message="button must be enter or select.",
                allowed_buttons=sorted(
                    LCD_BUTTON_MASKS
                ),
            )

        source = request.get(
            "source",
            "web",
        )

        if not isinstance(
            source,
            str,
        ):
            return _response(
                ok=False,
                status="invalid_request",
                message="source must be a string.",
            )

        source = source.strip().lower()

        if source != "web":
            return _response(
                ok=False,
                status="invalid_source",
                message="Virtual LCD commands must use source web.",
            )

        mask = LCD_BUTTON_MASKS[
            button
        ]

        try:
            accepted = bool(
                self.submit_button(
                    mask,
                    source,
                )
            )
        except Exception as error:
            LOGGER.exception(
                "Virtual LCD button submission failed"
            )
            return _response(
                ok=False,
                status="execution_failed",
                message=str(error),
            )

        if not accepted:
            return _response(
                ok=False,
                status="dispatcher_unavailable",
                message=(
                    "LCD dispatcher is not available."
                ),
            )

        return _response(
            ok=True,
            status="accepted",
            message=(
                f"Virtual {button} button accepted."
            ),
            button=button,
            button_mask=mask,
            source=source,
        )


class LCDCommandServer:
    """Unix-socket server owned by the production LCD service."""

    def __init__(
        self,
        processor: LCDCommandProcessor,
        path: str | Path = (
            DEFAULT_LCD_COMMAND_SOCKET_PATH
        ),
    ):
        self.processor = processor
        self.path = Path(path)

        self._socket = None
        self._thread = None
        self._stop_event = (
            threading.Event()
        )

    def start(self) -> None:
        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            return

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o755,
        )

        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

        server = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        server.bind(
            str(self.path)
        )
        server.listen(4)
        server.settimeout(0.25)

        self._socket = server
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._serve,
            name="truepanel-lcd-command",
            daemon=True,
        )
        self._thread.start()

        LOGGER.info(
            "LCD command socket listening at %s",
            self.path,
        )

    def _serve(self) -> None:
        while not self._stop_event.is_set():
            try:
                connection, _ = (
                    self._socket.accept()
                )
            except socket.timeout:
                continue
            except OSError:
                if self._stop_event.is_set():
                    return
                raise

            with connection:
                response = self._handle_connection(
                    connection
                )

                encoded = (
                    json.dumps(
                        response,
                        sort_keys=True,
                    ).encode("utf-8")
                    + b"\n"
                )

                try:
                    connection.sendall(
                        encoded
                    )
                except (
                    BrokenPipeError,
                    ConnectionResetError,
                ):
                    LOGGER.warning(
                        "LCD command completed, but the "
                        "client disconnected before receiving "
                        "the response."
                    )
                except OSError:
                    LOGGER.exception(
                        "Could not send LCD command response"
                    )

    def _handle_connection(
        self,
        connection: socket.socket,
    ) -> dict[str, Any]:
        chunks = []
        total = 0

        while total <= MAX_REQUEST_BYTES:
            chunk = connection.recv(
                min(
                    1024,
                    MAX_REQUEST_BYTES
                    + 1
                    - total,
                )
            )

            if not chunk:
                break

            chunks.append(
                chunk
            )
            total += len(
                chunk
            )

            if b"\n" in chunk:
                break

        if total > MAX_REQUEST_BYTES:
            return _response(
                ok=False,
                status="request_too_large",
                message=(
                    "LCD command exceeds the size limit."
                ),
            )

        raw = b"".join(
            chunks
        ).split(
            b"\n",
            1,
        )[0]

        try:
            request = json.loads(
                raw.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            return _response(
                ok=False,
                status="invalid_json",
                message="LCD command must contain valid JSON.",
            )

        return self.processor.process(
            request
        )

    def stop(self) -> None:
        self._stop_event.set()

        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

        if self._thread is not None:
            self._thread.join(
                timeout=2
            )
            self._thread = None

        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

        LOGGER.info(
            "LCD command socket stopped"
        )


class LCDCommandClient:
    """Mission Control client with no serial or LCD hardware imports."""

    def __init__(
        self,
        path: str | Path = (
            DEFAULT_LCD_COMMAND_SOCKET_PATH
        ),
        *,
        timeout: float = (
            DEFAULT_LCD_COMMAND_TIMEOUT
        ),
    ):
        self.path = Path(path)
        self.timeout = max(
            0.1,
            float(timeout),
        )

    def request(
        self,
        button: str,
    ) -> dict[str, Any]:
        payload = {
            "button": str(button),
            "source": "web",
        }

        encoded = (
            json.dumps(
                payload
            ).encode("utf-8")
            + b"\n"
        )

        client = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        client.settimeout(
            self.timeout
        )

        try:
            client.connect(
                str(self.path)
            )
            client.sendall(
                encoded
            )
            client.shutdown(
                socket.SHUT_WR
            )

            chunks = []

            while True:
                chunk = client.recv(
                    4096
                )

                if not chunk:
                    break

                chunks.append(
                    chunk
                )

                if b"\n" in chunk:
                    break
        except OSError as error:
            raise LCDCommandError(
                "LCD command socket is unavailable: "
                f"{error}"
            ) from error
        finally:
            client.close()

        raw = b"".join(
            chunks
        ).split(
            b"\n",
            1,
        )[0]

        try:
            response = json.loads(
                raw.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise LCDCommandError(
                "LCD command response was invalid."
            ) from error

        if not isinstance(
            response,
            dict,
        ):
            raise LCDCommandError(
                "LCD command response was not an object."
            )

        return response
