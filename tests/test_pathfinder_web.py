from __future__ import annotations

import copy
import http.client
import json
import threading
from pathlib import Path

from truepanel.guidance.recovery import recovery_contract
from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.web import pathfinder_server, service


class _SnapshotService:
    def __init__(self, payload):
        self.payload = payload

    def status(self):
        return copy.deepcopy(self.payload)


class _BayMirror:
    def snapshot(self):
        return {
            "schema_version": 1,
            "read_only_hardware": True,
            "privacy_safe": True,
            "available": True,
            "count": 0,
            "bays": [],
        }


def _guidance_card():
    card = {
        "code": "network.link_down",
        "severity": "warning",
        "summary": "Primary network link is down",
        "immediate_actions": [],
        "diagnosis": [],
        "remediation": [],
        "verification": [],
        "runtime": {
            "phase": "detected",
            "evidence": {
                "interface": "eth0",
                "link_up": False,
                "address": None,
            },
            "action_gate": {
                "safe_checks": True,
                "physical_service_ready": False,
                "destructive_actions_ready": False,
                "blocked_by": ["link_down"],
            },
        },
    }
    card["recovery"] = recovery_contract(card)
    return card


def _payload():
    return {
        "operator_guidance": [_guidance_card()],
        "health": {
            "subsystems": {
                "network": {
                    "state": "DEGRADED",
                }
            }
        },
        "storage": {},
    }


def _smart_lifeline_payload():
    card = {
        "code": "storage.smart_warning",
        "title": "Critical drive-health evidence detected",
        "summary": "Critical SMART evidence requires guided recovery.",
        "severity": "critical",
        "immediate_actions": [],
        "diagnosis": [],
        "remediation": [],
        "verification": [],
        "runtime": {
            "active": True,
            "phase": "diagnose",
            "evidence": {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "bay": 3,
                "device": "sda",
                "pending": 1608,
                "offline_uncorrectable": 1608,
            },
        },
        "repair_session": {
            "phase": "prepare",
            "phase_index": 3,
            "phase_count": 9,
            "title": "Guided drive recovery",
            "summary": "Verify service prerequisites before physical service.",
            "target": {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "member_id": "/dev/sda1",
                "bay": 3,
                "device": "sda",
                "trigger": "critical_smart_prefailure",
            },
            "gates": [
                {
                    "code": "member_identity",
                    "title": "Faulted member identified",
                    "detail": "Storage identity is verified.",
                    "risk": "safe",
                    "satisfied": True,
                },
                {
                    "code": "physical_identity",
                    "title": "Physical bay independently verified",
                    "detail": "Bay 3 is independently verified.",
                    "risk": "safe",
                    "satisfied": True,
                },
                {
                    "code": "replacement_candidate",
                    "title": "Replacement candidate validated",
                    "detail": "No replacement candidate is installed yet.",
                    "risk": "destructive",
                    "satisfied": False,
                },
            ],
            "can_identify_bay": True,
            "can_begin_physical_service": False,
            "can_prepare_replacement": False,
            "write_preconditions_complete": False,
            "can_execute_replacement": False,
            "blocked_by": ["replacement_candidate"],
            "warnings": [],
        },
    }
    return {
        "operator_guidance": [card],
        # Deliberately stale CHECKLIST state mirrors the live ordering bug that
        # BattleStation exposed after SMART Lifeline enriched guidance.
        "operator_checklists": [
            {
                "code": "storage.smart_warning",
                "active": True,
                "status": "ready",
                "target": {},
                "preflight": [],
                "progress": {"verified": 0, "total": 0},
                "capabilities": {"can_identify_bay": False},
                "read_only": True,
            }
        ],
        "health": {"subsystems": {"storage": {"state": "CRITICAL"}}},
        "storage": {},
    }


def _request(server, method, path, *, body=None, headers=None):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        payload = None
        request_headers = dict(headers or {})
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(payload))
        connection.request(method, path, body=payload, headers=request_headers)
        response = connection.getresponse()
        content = response.read()
        return response.status, response.getheader("Content-Type"), content
    finally:
        connection.close()


def _server(tmp_path, payload=None):
    server = pathfinder_server.MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=_SnapshotService(payload or _payload()),
        recovery_session_store=RecoverySessionStore(None),
        bay_mirror_provider=_BayMirror(),
        lifeline_identify_service=object(),
        config_path=tmp_path / "truepanel.yaml",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_production_service_uses_pathfinder_server():
    assert service.serve is pathfinder_server.serve


def test_status_publishes_durable_recovery_metadata(tmp_path):
    server, thread = _server(tmp_path)
    try:
        status, content_type, raw = _request(server, "GET", "/api/v1/status")
        assert status == 200
        assert content_type.startswith("application/json")
        payload = json.loads(raw)
        card = payload["operator_guidance"][0]
        assert card["recovery"]["state"] == "detected"
        recovery = payload["pathfinder_recovery"]
        assert recovery["metadata_only"] is True
        assert recovery["count"] == 1
        assert recovery["sessions"][0]["state"] == "detected"
        assert "interface" not in recovery["sessions"][0]
        assert "evidence" not in recovery["sessions"][0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_status_rebuilds_checklist_from_final_lifeline_guidance(tmp_path):
    server, thread = _server(tmp_path, _smart_lifeline_payload())
    try:
        status, _, raw = _request(server, "GET", "/api/v1/status")
        assert status == 200
        payload = json.loads(raw)

        guidance = payload["operator_guidance"][0]
        checklist = payload["operator_checklists"][0]

        assert guidance["repair_session"]["target"]["bay"] == 3
        assert checklist["code"] == "storage.smart_warning"
        assert checklist["recovery_kind"] == "drive_replacement"
        assert checklist["target"]["bay"] == 3
        assert checklist["target"]["device"] == "sda"
        assert checklist["capabilities"]["can_identify_bay"] is True
        assert checklist["progress"] == {"verified": 2, "total": 3}
        assert checklist["status"] == "hold"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_workflow_endpoint_requires_intent_and_rejects_manual_resolve(tmp_path):
    server, thread = _server(tmp_path)
    try:
        _, _, raw = _request(server, "GET", "/api/v1/status")
        incident_id = json.loads(raw)["operator_guidance"][0]["recovery"]["incident_id"]

        status, _, _ = _request(
            server,
            "POST",
            "/api/v1/recovery/transition",
            body={"incident_id": incident_id, "action": "begin_recovery"},
        )
        assert status == 403

        status, _, raw = _request(
            server,
            "POST",
            "/api/v1/recovery/transition",
            body={"incident_id": incident_id, "action": "resolved"},
            headers={"X-TruePanel-Intent": "pathfinder-recovery-transition"},
        )
        assert status == 422
        assert json.loads(raw)["error"] == "pathfinder_transition_rejected"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_workflow_endpoint_advances_metadata_without_mutation_authority(tmp_path):
    server, thread = _server(tmp_path)
    try:
        _, _, raw = _request(server, "GET", "/api/v1/status")
        incident_id = json.loads(raw)["operator_guidance"][0]["recovery"]["incident_id"]
        headers = {"X-TruePanel-Intent": "pathfinder-recovery-transition"}

        for action, expected in (
            ("begin_recovery", "reviewing"),
            ("begin_diagnosis", "diagnosing"),
            ("begin_repair", "repairing"),
            ("begin_verification", "verifying"),
        ):
            status, _, raw = _request(
                server,
                "POST",
                "/api/v1/recovery/transition",
                body={"incident_id": incident_id, "action": action},
                headers=headers,
            )
            assert status == 200
            result = json.loads(raw)
            assert result["session"]["state"] == expected
            assert result["workflow_only"] is True
            assert result["hardware_mutation"] is False
            assert result["storage_mutation"] is False
            assert result["verification_override"] is False

        status, _, raw = _request(server, "GET", "/api/v1/status")
        assert status == 200
        payload = json.loads(raw)
        assert payload["operator_guidance"][0]["recovery"]["state"] == "verifying"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_workflow_endpoint_rejects_arbitrary_state_or_extra_fields(tmp_path):
    server, thread = _server(tmp_path)
    try:
        _, _, raw = _request(server, "GET", "/api/v1/status")
        incident_id = json.loads(raw)["operator_guidance"][0]["recovery"]["incident_id"]
        headers = {"X-TruePanel-Intent": "pathfinder-recovery-transition"}

        status, _, _ = _request(
            server,
            "POST",
            "/api/v1/recovery/transition",
            body={
                "incident_id": incident_id,
                "action": "begin_recovery",
                "next_state": "resolved",
            },
            headers=headers,
        )
        assert status == 422
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_dashboard_serves_mobile_recovery_command_deck(tmp_path):
    server, thread = _server(tmp_path)
    try:
        status, content_type, body = _request(server, "GET", "/")
        assert status == 200
        assert content_type.startswith("text/html")
        assert b'/recovery-workflow.js' in body

        status, content_type, script = _request(server, "GET", "/recovery-workflow.js")
        assert status == 200
        assert content_type.startswith("application/javascript")
        source = script.decode("utf-8")
        assert 'TRANSITION_URL="/api/v1/recovery/transition"' in source
        assert 'X-TruePanel-Intent' in source
        assert 'verification_override' not in source
        assert 'data-pf-action="resolved"' not in source
        assert "@media(max-width:760px)" in source
        assert ".pf-action{width:100%}" in source
        for forbidden in (
            "/api/v1/fans/profile",
            "/api/v1/lifeline/identify",
            "/api/v1/lcd/button",
            "zpool replace",
            "pool.replace",
        ):
            assert forbidden not in source
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_recovery_ui_is_packaged_as_static_asset():
    script = Path(pathfinder_server.STATIC_DIR) / "recovery-workflow.js"
    assert script.is_file()
