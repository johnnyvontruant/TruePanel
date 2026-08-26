"""Mission Control integration for Project Pathfinder recovery workflow.

This module layers persistent recovery workflow metadata over the established
Mission Control server without changing any hardware, storage, fan, LCD, or
configuration authority. The only new POST surface advances bookkeeping state;
machine verification remains the sole path to ``resolved``.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import urlparse

from truepanel.guidance.sessions import RecoverySessionStore

from . import server as _server

STATIC_DIR = _server.STATIC_DIR
_RECOVERY_SCRIPT = "recovery-workflow.js"
_RECOVERY_MARKER = b"<!-- truepanel-pathfinder-recovery -->"
_RECOVERY_TAG = (
    _RECOVERY_MARKER
    + b'\n<script src="/recovery-workflow.js" defer></script>\n'
)
_RECOVERY_TRANSITION_PATH = "/api/v1/recovery/transition"
_RECOVERY_TRANSITION_INTENT = "pathfinder-recovery-transition"
_RECOVERY_ACTIONS = {
    "begin_recovery": ("reviewing", "operator_began_recovery"),
    "begin_diagnosis": ("diagnosing", "operator_began_diagnosis"),
    "begin_repair": ("repairing", "operator_began_repair"),
    "begin_verification": ("verifying", "operator_began_verification"),
    "return_to_diagnosis": ("diagnosing", "operator_returned_to_diagnosis"),
}


class MissionControlRequestHandler(_server.MissionControlRequestHandler):
    """Add Pathfinder workflow UI and metadata transitions."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == f"/{_RECOVERY_SCRIPT}":
            self._static_script(_RECOVERY_SCRIPT, "pathfinder_recovery_unavailable")
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == _RECOVERY_TRANSITION_PATH:
            self._recovery_transition(parsed)
            return
        super().do_POST()

    def _dashboard(self, parsed):
        del parsed
        candidate = STATIC_DIR / "index.html"
        try:
            body = candidate.read_bytes()
        except OSError:
            self._json(
                {"error": "dashboard_unavailable"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        tags = b""
        inherited = (
            (_server._FLIGHT_MANUAL_MARKER, _server._FLIGHT_MANUAL_TAG),
            (_server._COCKPIT_POLISH_MARKER, _server._COCKPIT_POLISH_TAG),
            (_server._COCKPIT_VARIANTS_MARKER, _server._COCKPIT_VARIANTS_TAG),
            (_server._LIFELINE_MARKER, _server._LIFELINE_TAG),
            (_server._LIFELINE_ACTIONS_MARKER, _server._LIFELINE_ACTIONS_TAG),
        )
        for marker, tag in inherited:
            if marker not in body:
                tags += tag
        if _RECOVERY_MARKER not in body:
            tags += _RECOVERY_TAG

        if tags:
            if b"</body>" in body:
                body = body.replace(b"</body>", tags + b"</body>", 1)
            else:
                body += tags

        self._send(body, content_type="text/html; charset=utf-8")

    def _status(self, parsed):
        del parsed
        payload = self.snapshot_service.status()
        if not isinstance(payload, dict):
            payload = {}
        else:
            payload = dict(payload)

        guidance = payload.get("operator_guidance")
        cards = guidance if isinstance(guidance, list) else []
        store = self.server.recovery_session_store
        payload["operator_guidance"] = store.observe_snapshot(cards, payload)
        payload["pathfinder_recovery"] = store.snapshot()

        storage = payload.get("storage")
        if not isinstance(storage, dict):
            storage = {}
        else:
            storage = dict(storage)

        try:
            mirror = self.server.bay_mirror_provider.snapshot()
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            mirror = {
                "schema_version": 1,
                "read_only_hardware": True,
                "privacy_safe": True,
                "available": False,
                "count": 0,
                "bays": [],
            }

        storage["bay_mirror"] = mirror
        payload["storage"] = storage
        self._json(payload)

    def _read_recovery_json(self, maximum=2048):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            content_length = 0
        if content_length < 1 or content_length > int(maximum):
            self._json(
                {
                    "error": "invalid_request",
                    "message": "Pathfinder workflow request body is invalid.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return None
        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(
                {
                    "error": "invalid_json",
                    "message": "Pathfinder workflow request body must contain valid JSON.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return None
        if not isinstance(body, dict):
            self._json(
                {
                    "error": "invalid_request",
                    "message": "Pathfinder workflow request body must be a JSON object.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return None
        return body

    def _recovery_transition(self, parsed):
        del parsed
        if self.headers.get("X-TruePanel-Intent", "") != _RECOVERY_TRANSITION_INTENT:
            self._json(
                {
                    "error": "pathfinder_intent_required",
                    "message": "Recovery workflow changes require an explicit same-origin intent header.",
                },
                status=HTTPStatus.FORBIDDEN,
            )
            return

        body = self._read_recovery_json()
        if body is None:
            return
        if set(body) - {"incident_id", "action"}:
            self._json(
                {
                    "error": "pathfinder_transition_rejected",
                    "message": "Recovery workflow accepts only incident_id and a named workflow action.",
                },
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        incident_id = str(body.get("incident_id") or "").strip()
        action = str(body.get("action") or "").strip().lower()
        transition = _RECOVERY_ACTIONS.get(action)
        if not incident_id or transition is None:
            self._json(
                {
                    "error": "pathfinder_transition_rejected",
                    "message": "Unknown or incomplete recovery workflow action.",
                },
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        next_state, event = transition
        try:
            session = self.server.recovery_session_store.transition(
                incident_id,
                next_state,
                event,
            )
        except KeyError:
            self._json(
                {"error": "pathfinder_incident_not_found"},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        except ValueError as error:
            self._json(
                {
                    "error": "pathfinder_transition_conflict",
                    "message": str(error),
                },
                status=HTTPStatus.CONFLICT,
            )
            return

        self._json(
            {
                "ok": True,
                "workflow_only": True,
                "hardware_mutation": False,
                "storage_mutation": False,
                "verification_override": False,
                "session": session,
            }
        )


class MissionControlServer(_server.MissionControlServer):
    """Use Pathfinder's handler while retaining established server state."""

    def __init__(
        self,
        address,
        snapshot_service=None,
        *,
        recovery_session_store=None,
        **kwargs,
    ):
        super().__init__(
            address,
            snapshot_service=snapshot_service,
            **kwargs,
        )
        self.recovery_session_store = (
            recovery_session_store or RecoverySessionStore()
        )
        self.RequestHandlerClass = MissionControlRequestHandler


def serve(
    host="127.0.0.1",
    port=8787,
    snapshot_service=None,
    *,
    allow_config_writes=False,
    config_path="truepanel.yaml",
    fan_command_client=None,
    lcd_command_client=None,
    lifeline_identify_service=None,
    bay_mirror_provider=None,
    recovery_session_store=None,
):
    server = MissionControlServer(
        (host, int(port)),
        snapshot_service=snapshot_service,
        allow_config_writes=allow_config_writes,
        config_path=config_path,
        fan_command_client=fan_command_client,
        lcd_command_client=lcd_command_client,
        lifeline_identify_service=lifeline_identify_service,
        bay_mirror_provider=bay_mirror_provider,
        recovery_session_store=recovery_session_store,
    )
    _server._base.LOGGER.info(
        "Mission Control listening on http://%s:%s",
        host,
        port,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser():
    return _server.build_parser()


def main():
    args = build_parser().parse_args()
    _server._base.logging.basicConfig(
        level=_server._base.logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    serve(
        host=args.host,
        port=args.port,
        allow_config_writes=args.allow_config_writes,
        config_path=args.config_path,
    )


if __name__ == "__main__":
    main()
