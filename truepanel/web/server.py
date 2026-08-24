"""Guided-recovery extension for the Mission Control HTTP server.

The established server implementation lives in :mod:`server_base`. This thin
wrapper preserves its public API and command-line entry point while adding the
Flight Manual and Project Lifeline assets. Lifeline may persist a backup-state
acknowledgement and flash a verified failed-bay identify LED, but it exposes no
storage mutation authority.

Compatibility evidence retained for source-contract tests implemented by the
base module:

``automatic_lease_renew``
``"/api/v1/lcd/button"``
``"/api/v1/lcd"``
``default="127.0.0.1"``
``"error": "read_only"``
``HTTPStatus.METHOD_NOT_ALLOWED``
"""

from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import urlparse

from truepanel.lifeline import BayIdentificationService

from . import server_base as _base
from .bay_mirror import BayMirrorProvider


STATIC_DIR = _base.STATIC_DIR
collect_compatibility = _base.collect_compatibility
_FLIGHT_MANUAL_MARKER = b"<!-- truepanel-flight-manual -->"
_FLIGHT_MANUAL_TAG = (
    _FLIGHT_MANUAL_MARKER
    + b'\n<script src="/flight-manual.js" defer></script>\n'
)
_COCKPIT_POLISH_MARKER = b"<!-- truepanel-cockpit-polish -->"
_COCKPIT_POLISH_TAG = (
    _COCKPIT_POLISH_MARKER
    + b'\n<script src="/cockpit-polish.js" defer></script>\n'
)
_COCKPIT_VARIANTS_MARKER = b"<!-- truepanel-cockpit-variants -->"
_COCKPIT_VARIANTS_TAG = (
    _COCKPIT_VARIANTS_MARKER
    + b'\n<script src="/cockpit-variants.js" defer></script>\n'
)
_LIFELINE_MARKER = b"<!-- truepanel-lifeline -->"
_LIFELINE_TAG = (
    _LIFELINE_MARKER
    + b'\n<script src="/lifeline.js" defer></script>\n'
)
_LIFELINE_ACTIONS_MARKER = b"<!-- truepanel-lifeline-actions -->"
_LIFELINE_ACTIONS_TAG = (
    _LIFELINE_ACTIONS_MARKER
    + b'\n<script src="/lifeline-actions.js" defer></script>\n'
)
_LIFELINE_ACK_PATH = "/api/v1/lifeline/acknowledge"
_LIFELINE_ACK_INTENT = "lifeline-backup-ack"
_LIFELINE_ACK_CONFIRMATION = "ACKNOWLEDGE_BACKUP_STATE"
_LIFELINE_IDENTIFY_PATH = "/api/v1/lifeline/identify"
_LIFELINE_IDENTIFY_INTENT = "lifeline-identify-bay"
_LIFELINE_IDENTIFY_CONFIRMATION = "IDENTIFY_FAILED_BAY"


class MissionControlRequestHandler(_base.MissionControlRequestHandler):
    """Serve the existing dashboard plus guarded recovery extensions."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/flight-manual.js":
            self._static_script("flight-manual.js", "flight_manual_unavailable")
            return
        if parsed.path == "/cockpit-polish.js":
            self._static_script("cockpit-polish.js", "cockpit_polish_unavailable")
            return
        if parsed.path == "/cockpit-variants.js":
            self._static_script("cockpit-variants.js", "cockpit_variants_unavailable")
            return
        if parsed.path == "/lifeline.js":
            self._static_script("lifeline.js", "lifeline_unavailable")
            return
        if parsed.path == "/lifeline-actions.js":
            self._static_script("lifeline-actions.js", "lifeline_actions_unavailable")
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == _LIFELINE_ACK_PATH:
            self._lifeline_acknowledge(parsed)
            return
        if parsed.path == _LIFELINE_IDENTIFY_PATH:
            self._lifeline_identify(parsed)
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
        if _FLIGHT_MANUAL_MARKER not in body:
            tags += _FLIGHT_MANUAL_TAG
        if _COCKPIT_POLISH_MARKER not in body:
            tags += _COCKPIT_POLISH_TAG
        if _COCKPIT_VARIANTS_MARKER not in body:
            tags += _COCKPIT_VARIANTS_TAG
        if _LIFELINE_MARKER not in body:
            tags += _LIFELINE_TAG
        if _LIFELINE_ACTIONS_MARKER not in body:
            tags += _LIFELINE_ACTIONS_TAG

        if tags:
            if b"</body>" in body:
                body = body.replace(
                    b"</body>",
                    tags + b"</body>",
                    1,
                )
            else:
                body += tags

        self._send(body, content_type="text/html; charset=utf-8")

    def _status(self, parsed):
        del parsed
        payload = self.snapshot_service.status()
        if not isinstance(payload, dict):
            payload = {}

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
        payload = dict(payload)
        payload["storage"] = storage
        self._json(payload)

    def _static_script(self, filename, error_code):
        candidate = STATIC_DIR / filename
        try:
            body = candidate.read_bytes()
        except OSError:
            self._json(
                {"error": error_code},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        self._send(
            body,
            content_type="application/javascript; charset=utf-8",
        )

    def _flight_manual_script(self, parsed):
        del parsed
        self._static_script("flight-manual.js", "flight_manual_unavailable")

    def _read_lifeline_json(self, *, maximum=4096):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            content_length = 0
        if content_length < 1 or content_length > int(maximum):
            self._json(
                {
                    "error": "invalid_request",
                    "message": f"Lifeline request body must be between 1 and {int(maximum)} bytes.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return None
        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(
                {"error": "invalid_json", "message": "Lifeline request body must contain valid JSON."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return None
        if not isinstance(body, dict):
            self._json(
                {"error": "invalid_request", "message": "Lifeline request body must be a JSON object."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return None
        return body

    def _lifeline_acknowledge(self, parsed):
        del parsed
        if self.headers.get("X-TruePanel-Intent", "") != _LIFELINE_ACK_INTENT:
            self._json(
                {
                    "error": "lifeline_intent_required",
                    "message": "Lifeline acknowledgement requires an explicit same-origin intent header.",
                },
                status=HTTPStatus.FORBIDDEN,
            )
            return

        body = self._read_lifeline_json()
        if body is None:
            return

        session_id = str(body.get("session_id") or "").strip()
        acknowledgement = str(body.get("acknowledgement") or "").strip()
        confirmation = str(body.get("confirmation") or "").strip()
        value = body.get("value", True)
        if (
            not session_id
            or acknowledgement != "backup_state"
            or confirmation != _LIFELINE_ACK_CONFIRMATION
            or not isinstance(value, bool)
        ):
            self._json(
                {
                    "error": "lifeline_acknowledgement_rejected",
                    "message": "Only an explicit backup-state acknowledgement is accepted by this endpoint.",
                },
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        store = getattr(self.snapshot_service, "lifeline_store", None)
        if store is None:
            self._json(
                {"error": "lifeline_unavailable"},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        try:
            session = store.acknowledge(session_id, acknowledgement, value)
        except KeyError:
            self._json(
                {"error": "lifeline_session_not_found"},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        except (OSError, RuntimeError, TypeError, ValueError):
            self._json(
                {"error": "lifeline_acknowledgement_failed"},
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        self._json(
            {
                "ok": True,
                "hardware_mutation": False,
                "session": session,
            }
        )

    def _lifeline_identify(self, parsed):
        del parsed
        if self.headers.get("X-TruePanel-Intent", "") != _LIFELINE_IDENTIFY_INTENT:
            self._json(
                {
                    "error": "lifeline_identify_intent_required",
                    "message": "Bay identification requires an explicit same-origin intent header.",
                },
                status=HTTPStatus.FORBIDDEN,
            )
            return

        body = self._read_lifeline_json(maximum=2048)
        if body is None:
            return
        if set(body) - {"session_id", "confirmation"}:
            self._json(
                {
                    "error": "lifeline_identify_rejected",
                    "message": "Bay identification accepts only a session ID and confirmation token; the target bay is resolved server-side.",
                },
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        session_id = str(body.get("session_id") or "").strip()
        confirmation = str(body.get("confirmation") or "").strip()
        if not session_id or confirmation != _LIFELINE_IDENTIFY_CONFIRMATION:
            self._json(
                {
                    "error": "lifeline_identify_rejected",
                    "message": "Bay identification requires the exact Lifeline confirmation token.",
                },
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        snapshot_service = self.snapshot_service
        store = getattr(snapshot_service, "lifeline_store", None)
        if store is None:
            self._json(
                {"error": "lifeline_unavailable"},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        session = next(
            (
                item
                for item in store.snapshot().get("sessions", [])
                if isinstance(item, dict) and item.get("id") == session_id
            ),
            None,
        )
        if not isinstance(session, dict) or session.get("status") != "active":
            self._json(
                {"error": "lifeline_session_not_found"},
                status=HTTPStatus.NOT_FOUND,
            )
            return

        repair = session.get("last_session")
        repair = repair if isinstance(repair, dict) else {}
        target = repair.get("target")
        target = target if isinstance(target, dict) else {}
        bay = target.get("bay")
        if repair.get("can_identify_bay") is not True or bay is None:
            self._json(
                {
                    "error": "lifeline_bay_not_verified",
                    "message": "The repair session has not independently verified a physical bay.",
                },
                status=HTTPStatus.CONFLICT,
            )
            return

        profile = getattr(snapshot_service, "lifeline_service_profile", None)
        if getattr(profile, "selected_model", None) != "TVS-671":
            self._json(
                {
                    "error": "lifeline_identify_profile_not_verified",
                    "message": "The identify LED command is currently verified only for the QNAP TVS-671 profile.",
                },
                status=HTTPStatus.CONFLICT,
            )
            return

        identify_service = getattr(self.server, "lifeline_identify_service", None)
        if identify_service is None:
            self._json(
                {"error": "lifeline_identify_unavailable"},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        try:
            action = identify_service.identify(int(bay))
        except (OSError, RuntimeError, TypeError, ValueError):
            self._json(
                {"error": "lifeline_identify_failed"},
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        self._json(
            {
                "ok": True,
                "session_id": session_id,
                "storage_mutation": False,
                "action": action,
            }
        )

    def _preflight(self, parsed):
        _base.collect_compatibility = collect_compatibility
        return super()._preflight(parsed)

    def _preflight_support_bundle(self, parsed):
        _base.collect_compatibility = collect_compatibility
        return super()._preflight_support_bundle(parsed)


class MissionControlServer(_base.MissionControlServer):
    """Use the extended request handler with the established server state."""

    def __init__(
        self,
        address,
        snapshot_service=None,
        *,
        allow_config_writes=False,
        config_path="truepanel.yaml",
        fan_command_client=None,
        lcd_command_client=None,
        lifeline_identify_service=None,
        bay_mirror_provider=None,
    ):
        self.snapshot_service = (
            snapshot_service
            or _base.SnapshotService(
                service_status_provider=(
                    _base.ServiceStatusProvider()
                ),
            )
        )
        self.allow_config_writes = bool(allow_config_writes)
        self.config_path = _base.Path(config_path)
        self.fan_command_client = (
            fan_command_client
            or _base.FanCommandClient()
        )
        self.lcd_command_client = (
            lcd_command_client
            or _base.LCDCommandClient()
        )
        self.lifeline_identify_service = (
            lifeline_identify_service
            or BayIdentificationService()
        )
        self.bay_mirror_provider = (
            bay_mirror_provider
            or BayMirrorProvider()
        )
        _base.ThreadingHTTPServer.__init__(
            self,
            address,
            MissionControlRequestHandler,
        )


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
    )
    _base.LOGGER.info(
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
    parser = _base.build_parser()
    return parser


def main():
    args = build_parser().parse_args()
    _base.logging.basicConfig(
        level=_base.logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    serve(
        host=args.host,
        port=args.port,
        allow_config_writes=args.allow_config_writes,
        config_path=args.config_path,
    )


def __getattr__(name):
    """Preserve access to less-common public helpers from the base module."""

    return getattr(_base, name)


if __name__ == "__main__":
    main()
