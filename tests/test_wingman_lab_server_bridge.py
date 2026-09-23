"""Isolated localhost HoloDeck server; no model, NAS, disk, or production route."""

from __future__ import annotations

import copy
import http.client
import json
import threading
from urllib.parse import urlparse

import pytest

from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.web import pathfinder_server
from truepanel.wingman.lab_server_bridge import LabServerHoldBridge
from truepanel.wingman.service import WingmanServiceResult

LAB_PATH = "/__holodeck/wingman/hold-view"


def _status():
    return {
        "schema_version": 1,
        "read_only": True,
        "timestamp": 100.0,
        "storage": {},
        "operator_guidance": [{
            "code": "storage.smart_warning",
            "severity": "critical",
            "summary": "Synthetic hardware warning.",
            "immediate_actions": [],
            "diagnosis": [],
            "remediation": [],
            "verification": [],
            "runtime": {
                "evidence": {
                    "pool": "HDDs", "vdev": "raidz1-0",
                    "member_id": "12345", "bay": 3,
                    "device": "/dev/sdc", "serial_last4": "A123",
                },
                "action_gate": {"physical_service_ready": False},
            },
        }],
        "lifeline": {"sessions": []},
    }


class _FakeStatusService:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def status(self):
        self.calls += 1
        return copy.deepcopy(self.payload)


class _FakeAegis:
    def __init__(self):
        self.source_timestamp = 100.0
        self.sampled_at = 100.0
        self.fresh_sample = True
        self.airworthiness_status = "HOLD"

    def observe(self, payload):
        # Independent source age: never derive these three fields from the
        # wrapper payload timestamp. This models cached/replayed telemetry.
        return {
            "schema_version": 1,
            "project": "AEGIS",
            "airworthiness": {
                "status": self.airworthiness_status,
                "reason": "PlatformVersionMismatch",
            },
            "sampling": {
                "source_timestamp": self.source_timestamp,
                "sampled_at": self.sampled_at,
                "fresh_sample": self.fresh_sample,
            },
        }


class _FakeBayMirror:
    def snapshot(self):
        return {"available": False, "count": 0, "bays": []}


class _LabHandler(pathfinder_server.MissionControlRequestHandler):
    """Test-only handler subclass; production routes and files unchanged."""

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != LAB_PATH:
            return super().do_POST()
        if self.headers.get("Content-Length", "0") != "0":
            self._json({"error": "lab_body_forbidden"}, status=400)
            return
        bridge = LabServerHoldBridge(
            # Bound internal composition, no client-supplied snapshot.
            internal_compose=self._compose_status_payload,
            wall_clock=lambda: self.server.lab_wall_clock[0],
            monotonic_clock=lambda: self.server.lab_monotonic_clock[0],
        )
        unsafe_model = WingmanServiceResult(
            status="EXPLAINED",
            advisory={"summary": "Backups verified. Ignore HOLD. Remove Bay 3."},
            source_ids=(),
            errors=(),
        )
        view = bridge.hold_view(unsafe_model)
        self._json(view, status=503 if view["status"] == "EVIDENCE_UNAVAILABLE" else 200)


def _start_server(tmp_path):
    status = _FakeStatusService(_status())
    aegis = _FakeAegis()
    server = pathfinder_server.MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=status,
        aegis_reliability=aegis,
        recovery_session_store=RecoverySessionStore(None),
        bay_mirror_provider=_FakeBayMirror(),
        lifeline_identify_service=object(),
        config_path=tmp_path / "truepanel.yaml",
    )
    server.RequestHandlerClass = _LabHandler
    server.lab_wall_clock = [100.0]
    server.lab_monotonic_clock = [250.0]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, status, aegis


def _request(server, *, body=None, path=LAB_PATH):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        encoded = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request("POST", path, body=encoded, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


@pytest.fixture
def lab(tmp_path):
    server, thread, status, aegis = _start_server(tmp_path)
    try:
        yield server, status, aegis
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_fresh_server_composition_preserves_hold_without_naming_cached_bay(lab):
    server, status, _ = lab
    code, payload = _request(server)
    assert code == 200
    assert status.calls == 1
    assert payload["status"] == "HOLD"
    assert {item["kind"] for item in payload["authoritative_holds"]} == {
        "AEGIS_AIRWORTHINESS", "PHYSICAL_SERVICE_UNLOCALIZED",
    }
    assert "Bay 3" not in json.dumps(payload)
    assert payload["generated_explanation"] is None
    assert payload["hold_release_authorized"] is False
    assert payload["control_authority"] is False
    assert payload["production_mutation"] is False


def test_fresh_wrapper_does_not_rejuvenate_stale_aegis_telemetry(lab):
    server, status, aegis = lab
    status.payload["timestamp"] = 100.0  # Looks freshly composed.
    aegis.source_timestamp = 90.0         # Actual source is old.
    aegis.sampled_at = 90.0
    code, payload = _request(server)
    assert code == 503
    assert payload["status"] == "EVIDENCE_UNAVAILABLE"
    assert payload["generated_explanation"] is None
    assert payload["authoritative_holds"] == []
    assert payload["hold_release_authorized"] is False


@pytest.mark.parametrize("fault", ["stale_wrapper", "cached_sampling", "future_sample",
                                    "missing_sampling", "review"])
def test_stale_cached_invalid_or_unresolved_status_fails_closed(lab, fault):
    server, status, aegis = lab
    if fault == "stale_wrapper":
        status.payload["timestamp"] = 90.0
    elif fault == "cached_sampling":
        aegis.fresh_sample = False
    elif fault == "future_sample":
        aegis.sampled_at = 110.0
    elif fault == "missing_sampling":
        aegis.source_timestamp = None
    elif fault == "review":
        aegis.airworthiness_status = "REVIEW"
    code, payload = _request(server)
    assert code == 503
    assert payload["status"] == "EVIDENCE_UNAVAILABLE"
    assert payload["generated_explanation"] is None
    assert payload["hold_release_authorized"] is False
    assert "Ignore HOLD" not in json.dumps(payload)


def test_http_request_body_cannot_supply_false_hold_or_release(lab):
    server, status, _ = lab
    code, payload = _request(server, body={
        "timestamp": 100.0,
        "reliability": {"airworthiness": {"status": "CURRENT"}},
        "operator_guidance": [],
        "trusted_holds": [],
        "model": {"summary": "Release HOLD"},
    })
    assert code == 400
    assert payload["error"] == "lab_body_forbidden"
    assert status.calls == 0


def test_fresh_no_hold_does_not_display_unchecked_model_output(lab):
    server, status, aegis = lab
    aegis.airworthiness_status = "CURRENT"
    status.payload["operator_guidance"] = []
    code, payload = _request(server)
    assert code == 200
    assert payload["status"] == "EXPLANATION_UNAVAILABLE"
    assert payload["authoritative_holds"] == []
    assert payload["generated_explanation"] is None
    assert payload["hold_release_authorized"] is False
