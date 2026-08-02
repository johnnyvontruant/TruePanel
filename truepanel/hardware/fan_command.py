"""
Local Unix-socket command channel for root-owned fan control.

The socket accepts a deliberately narrow JSON protocol. Only Automatic and
Afterburners are exposed until lower PWM profiles have completed live RPM-floor
validation.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

LOGGER = logging.getLogger(__name__)

DEFAULT_FAN_CONTROL_SOCKET_PATH = Path(
    "/run/truepanel/fan-control.sock"
)

AFTERBURNERS_CONFIRMATION = (
    "ENGAGE_AFTERBURNERS"
)

THERMAL_ARM_CONFIRMATION = (
    "ARM_THERMAL_CONTROL"
)

SUPERVISED_THERMAL_CONFIRMATION = (
    "ENGAGE_SUPERVISED_THERMAL_CONTROL"
)

BOUNDED_AUTOMATIC_CONFIRMATION = (
    "ENGAGE_STAGE_3_AUTOMATIC_CONTROL"
)

BOUNDED_AUTOMATIC_RENEW_CONFIRMATION = (
    "RENEW_STAGE_3_AUTOMATIC_CONTROL"
)

THERMAL_CONTROL_COMMAND = "thermal_control"
THERMAL_ARM_ACTION = "arm"
THERMAL_DISARM_ACTION = "disarm"
THERMAL_SUPERVISED_ACTION = "supervised_live"
THERMAL_AUTOMATIC_LEASE_ACTION = "automatic_lease"
THERMAL_AUTOMATIC_RENEW_ACTION = "automatic_lease_renew"

MAX_REQUEST_BYTES = 4096

DEFAULT_FAN_COMMAND_RESPONSE_TIMEOUT = 10.0

AUTOMATIC_PROFILE = "automatic"
AFTERBURNERS_PROFILE = "afterburners"

ALLOWED_COMMAND_PROFILES = frozenset(
    {
        AUTOMATIC_PROFILE,
        AFTERBURNERS_PROFILE,
    }
)


class FanCommandError(RuntimeError):
    """Raised when a fan-control command cannot be completed."""


def _response(
    *,
    ok: bool,
    status: str,
    message: str,
    **extra,
) -> dict[str, Any]:
    payload = {
        "ok": bool(ok),
        "status": str(status),
        "message": str(message),
    }
    payload.update(
        extra
    )
    return payload


class FanCommandProcessor:
    """Validate local requests before calling the root-owned runtime."""

    def __init__(
        self,
        runtime,
        *,
        telemetry_provider: Callable[
            [],
            Mapping[str, Any],
        ],
        status_publisher: Callable[
            [],
            None,
        ] | None = None,
        event_recorder: Callable[
            [
                Any,
                Mapping[str, Any],
            ],
            None,
        ] | None = None,
        thermal_control_handler: Callable[
            [str],
            Mapping[str, Any],
        ] | None = None,
    ):
        self.runtime = runtime
        self.telemetry_provider = (
            telemetry_provider
        )
        self.status_publisher = (
            status_publisher
        )
        self.event_recorder = (
            event_recorder
        )
        self.thermal_control_handler = (
            thermal_control_handler
        )

    def _process_control_command(
        self,
        request: Mapping[str, Any],
        command: str,
    ) -> dict[str, Any]:
        if command != THERMAL_CONTROL_COMMAND:
            return _response(
                ok=False,
                status="unknown_command",
                message="Unknown fan-control command.",
            )

        action = str(
            request.get(
                "action",
                "",
            )
        ).strip().lower()

        if action not in {
            THERMAL_ARM_ACTION,
            THERMAL_DISARM_ACTION,
            THERMAL_SUPERVISED_ACTION,
            THERMAL_AUTOMATIC_LEASE_ACTION,
            THERMAL_AUTOMATIC_RENEW_ACTION,
        }:
            return _response(
                ok=False,
                status="invalid_action",
                message=(
                    "Thermal-control action must be arm, disarm, "
                    "supervised_live, automatic_lease, or "
                    "automatic_lease_renew."
                ),
                allowed_actions=[
                    THERMAL_ARM_ACTION,
                    THERMAL_DISARM_ACTION,
                    THERMAL_SUPERVISED_ACTION,
                    THERMAL_AUTOMATIC_LEASE_ACTION,
                    THERMAL_AUTOMATIC_RENEW_ACTION,
                ],
            )

        required_confirmation = None

        if action == THERMAL_ARM_ACTION:
            required_confirmation = (
                THERMAL_ARM_CONFIRMATION
            )
        elif action == THERMAL_SUPERVISED_ACTION:
            required_confirmation = (
                SUPERVISED_THERMAL_CONFIRMATION
            )
        elif action == THERMAL_AUTOMATIC_LEASE_ACTION:
            required_confirmation = (
                BOUNDED_AUTOMATIC_CONFIRMATION
            )
        elif action == THERMAL_AUTOMATIC_RENEW_ACTION:
            required_confirmation = (
                BOUNDED_AUTOMATIC_RENEW_CONFIRMATION
            )

        if (
            required_confirmation is not None
            and request.get("confirmation")
            != required_confirmation
        ):
            return _response(
                ok=False,
                status="confirmation_required",
                message=(
                    "This thermal-control action "
                    "requires explicit confirmation."
                ),
                confirmation_required=(
                    required_confirmation
                ),
            )

        if self.thermal_control_handler is None:
            return _response(
                ok=False,
                status="unsupported",
                message=(
                    "Runtime thermal-control arming "
                    "is unavailable."
                ),
            )

        try:
            result = dict(
                self.thermal_control_handler(
                    action
                )
                or {}
            )
        except Exception as error:
            LOGGER.exception(
                "Thermal-control command failed"
            )
            return _response(
                ok=False,
                status="execution_failed",
                message=(
                    "Thermal-control command failed."
                ),
                error=(
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )

        if self.status_publisher is not None:
            try:
                self.status_publisher()
            except Exception:
                LOGGER.exception(
                    "Could not publish fan status "
                    "after thermal-control command"
                )

        result.setdefault(
            "ok",
            True,
        )
        result.setdefault(
            "status",
            (
                "armed"
                if action == THERMAL_ARM_ACTION
                else "disarmed"
            ),
        )
        result.setdefault(
            "message",
            (
                "Automatic thermal control armed."
                if action == THERMAL_ARM_ACTION
                else (
                    "Automatic thermal control "
                    "disarmed."
                )
            ),
        )
        result.setdefault(
            "action",
            action,
        )

        return result

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
                message=(
                    "Command body must be "
                    "a JSON object."
                ),
            )

        command = str(
            request.get(
                "command",
                "",
            )
        ).strip().lower()

        if command:
            return self._process_control_command(
                request,
                command,
            )

        profile = str(
            request.get(
                "profile",
                "",
            )
        ).strip().lower()

        allowed_profiles = {
            "automatic",
            "quiet",
            "balanced",
            "cooling_boost",
            "afterburners",
        }

        if profile not in allowed_profiles:
            return _response(
                ok=False,
                status="unknown_profile",
                message=(
                    "Unknown fan profile."
                ),
                allowed_profiles=sorted(
                    allowed_profiles
                ),
            )

        if not self.runtime.enabled:
            return _response(
                ok=False,
                status="disabled",
                message=(
                    "Fan control is disabled."
                ),
            )

        if not self.runtime.connected:
            return _response(
                ok=False,
                status="disconnected",
                message=(
                    "Fan control runtime is "
                    "not connected."
                ),
            )

        if (
            profile
            == AFTERBURNERS_PROFILE
            and request.get(
                "confirmation"
            )
            != AFTERBURNERS_CONFIRMATION
        ):
            return _response(
                ok=False,
                status="confirmation_required",
                message=(
                    "Afterburners requires "
                    "explicit confirmation."
                ),
                confirmation_required=(
                    AFTERBURNERS_CONFIRMATION
                ),
            )

        try:
            telemetry = dict(
                self.telemetry_provider()
                or {}
            )
        except Exception as error:
            LOGGER.exception(
                "Fan command telemetry provider failed"
            )
            return _response(
                ok=False,
                status="telemetry_unavailable",
                message=(
                    "Current fan telemetry "
                    "could not be obtained."
                ),
                error=(
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )

        fan_status = telemetry.get(
            "fan_status",
            {},
        )
        temperatures_c = telemetry.get(
            "temperatures_c",
            (),
        )
        telemetry_fresh = bool(
            telemetry.get(
                "telemetry_fresh",
                True,
            )
        )

        try:
            decision = (
                self.runtime.service
                .request_profile(
                    profile,
                    fan_status=fan_status,
                    temperatures_c=(
                        temperatures_c
                    ),
                    telemetry_fresh=(
                        telemetry_fresh
                    ),
                )
            )
        except Exception as error:
            LOGGER.exception(
                "Fan command execution failed"
            )
            return _response(
                ok=False,
                status="execution_failed",
                message=(
                    "Fan-control command failed."
                ),
                error=(
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )

        if self.event_recorder is not None:
            try:
                self.event_recorder(
                    decision,
                    telemetry,
                )
            except Exception:
                LOGGER.exception(
                    "Could not record fan-control event"
                )

        if self.status_publisher is not None:
            try:
                self.status_publisher()
            except Exception:
                LOGGER.exception(
                    "Could not publish fan status "
                    "after command"
                )

        runtime_status = (
            self.runtime.status_payload()
        )

        return _response(
            ok=True,
            status="applied",
            message=decision.reason,
            requested_profile=(
                decision.requested_profile.value
            ),
            effective_profile=(
                decision.effective_profile.value
            ),
            accepted=bool(
                decision.accepted
            ),
            pwm=decision.pwm,
            force_automatic=bool(
                decision.force_automatic
            ),
            runtime=runtime_status,
        )


class FanCommandServer:
    """Small threaded Unix-domain socket server."""

    def __init__(
        self,
        processor: FanCommandProcessor,
        *,
        path: str | Path = (
            DEFAULT_FAN_CONTROL_SOCKET_PATH
        ),
        socket_mode: int = 0o660,
    ):
        self.processor = processor
        self.path = Path(
            path
        )
        self.socket_mode = int(
            socket_mode
        )
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = (
            threading.Event()
        )

    @property
    def running(self) -> bool:
        return bool(
            self._thread
            and self._thread.is_alive()
        )

    def start(self) -> None:
        if self.running:
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

        server_socket = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        server_socket.bind(
            str(self.path)
        )
        os.chmod(
            self.path,
            self.socket_mode,
        )
        server_socket.listen(
            8
        )
        server_socket.settimeout(
            0.5
        )

        self._socket = server_socket
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._serve,
            name="fan-command-server",
            daemon=True,
        )
        self._thread.start()

        LOGGER.info(
            "Fan command socket listening at %s",
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
                    ).encode(
                        "utf-8"
                    )
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
                        "Fan command completed, but the "
                        "client disconnected before the "
                        "response was delivered."
                    )
                except OSError:
                    LOGGER.exception(
                        "Could not send fan command response"
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
                    "Fan-control request "
                    "exceeds the size limit."
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
                raw.decode(
                    "utf-8"
                )
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            return _response(
                ok=False,
                status="invalid_json",
                message=(
                    "Request must contain "
                    "valid JSON."
                ),
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
            "Fan command socket stopped"
        )


class FanCommandClient:
    """JSON client used by Mission Control without importing fan hardware."""

    def __init__(
        self,
        path: str | Path = (
            DEFAULT_FAN_CONTROL_SOCKET_PATH
        ),
        *,
        timeout: float = (
            DEFAULT_FAN_COMMAND_RESPONSE_TIMEOUT
        ),
    ):
        self.path = Path(path)
        self.timeout = max(
            0.1,
            float(timeout),
        )

    def _exchange(
        self,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        encoded = (
            json.dumps(
                dict(payload)
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
            raise FanCommandError(
                "Fan command socket is unavailable: "
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
            raise FanCommandError(
                "Fan command response was invalid."
            ) from error

        if not isinstance(
            response,
            dict,
        ):
            raise FanCommandError(
                "Fan command response was not an object."
            )

        return response

    def request(
        self,
        profile: str,
        *,
        confirmation: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "profile": str(profile),
        }

        if confirmation is not None:
            payload[
                "confirmation"
            ] = confirmation

        return self._exchange(
            payload
        )

    def request_thermal_control(
        self,
        action: str,
        *,
        confirmation: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "command": THERMAL_CONTROL_COMMAND,
            "action": str(action),
        }

        if confirmation is not None:
            payload[
                "confirmation"
            ] = confirmation

        return self._exchange(
            payload
        )
