"""Friendly fault view: injection, authority boundary and plain-language model."""

from __future__ import annotations

import http.client
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.web import pathfinder_server

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "truepanel/web/static/fault-view.js"


class _SnapshotService:
    def status(self):
        return {
            "timestamp": 1,
            "operator_guidance": [],
            "storage": {},
            "fans": {},
            "network": [],
        }


class _BayMirror:
    def snapshot(self):
        return {"available": True, "count": 0, "bays": []}

    def device_bay_map(self):
        return {}


def _request(server, path):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        connection.close()


def test_dashboard_injects_and_serves_fault_view(tmp_path):
    server = pathfinder_server.MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=_SnapshotService(),
        recovery_session_store=RecoverySessionStore(None),
        bay_mirror_provider=_BayMirror(),
        lifeline_identify_service=object(),
        config_path=tmp_path / "truepanel.yaml",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, content_type, dashboard = _request(server, "/")
        assert status == 200
        assert content_type.startswith("text/html")
        assert b"<!-- truepanel-fault-view -->" in dashboard
        assert b'<script src="/fault-view.js" defer></script>' in dashboard
        # Loads after the panels it adopts into the Technical details drawer.
        assert dashboard.index(b"/reliability-view.js") < dashboard.index(
            b"/fault-view.js"
        )

        status, content_type, script = _request(server, "/fault-view.js")
        assert status == 200
        assert content_type.startswith("application/javascript")
        assert "friendlyFaultView" in script.decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_fault_view_uses_only_existing_guarded_lifeline_actions():
    source = SCRIPT.read_text(encoding="utf-8")
    urls = set(re.findall(r'"(/api/v1/[a-z0-9/_-]+)"', source))
    assert urls == {
        "/api/v1/status",
        "/api/v1/lifeline/acknowledge",
        "/api/v1/lifeline/identify",
    }
    assert source.count('method:"POST"') == 1
    assert '"ACKNOWLEDGE_BACKUP_STATE"' in source
    assert '"IDENTIFY_FAILED_BAY"' in source
    assert '"lifeline-backup-ack"' in source
    assert '"lifeline-identify-bay"' in source
    for forbidden in (
        "DELETE",
        "PUT",
        "/api/v1/recovery",
        "/api/v1/fans",
        "/api/v1/lcd",
    ):
        assert forbidden not in source
    # Engineering panels are moved into the drawer, never removed.
    assert ".remove()" not in source
    assert "drawerBody.append(el)" in source
    # Local ticks never stand in for machine-verified gates.
    assert "noManualTick:true" in source
    assert "localStorage" in source


def _fixture():
    """A synthetic, privacy-safe status payload shaped like a live bay fault."""

    def drive(bay, device, serial, state="ONLINE", present=True):
        return {
            "device": device,
            "physical_bay": bay,
            "label": f"Bay {bay}",
            "pool": "tank",
            "vdev": "raidz1-0",
            "vdev_topology": "RAIDZ1",
            "remaining_redundancy": 0,
            "zfs_state": state,
            "present": present,
            "model": "ST8000NE001-2M71",
            "serial_last4": serial,
            "capacity_bytes": 8001563222016,
            "read_errors": 0,
            "write_errors": 0,
            "checksum_errors": 0,
            "member_id": f"/dev/{device}1",
        }

    faulted = drive(None, None, None, state="FAULTED", present=False)
    faulted.update(
        {
            "member_id": "/dev/sdz1",
            "model": None,
            "serial_last4": None,
            "capacity_bytes": None,
            "read_errors": 12,
            "checksum_errors": 2,
        }
    )
    devices = [drive(1, "sda", "AAA1"), drive(2, "sdb", "AAA2"), faulted]
    return {
        "timestamp": 1,
        "health": {"state": "CRITICAL", "subsystems": {}},
        "operator_guidance": [
            {
                "code": "storage.disk_faulted",
                "summary": "x",
                "runtime": {"active": True},
            },
            {
                "code": "storage.pool_degraded",
                "summary": "x",
                "runtime": {"active": True},
            },
        ],
        "operator_checklists": [
            {
                "code": "storage.disk_faulted",
                "active": True,
                "preflight": [
                    {
                        "key": "member_identity",
                        "state": "verified",
                        "title": "Faulted member identified",
                    },
                    {
                        "key": "physical_identity",
                        "state": "hold",
                        "title": "Physical bay independently verified",
                    },
                ],
            },
        ],
        "storage": {
            "devices": devices,
            "pools": [
                {
                    "name": "tank",
                    "size": "21.8T",
                    "free": "2.0T",
                    "capacity": "90%",
                    "health": "DEGRADED",
                }
            ],
            "smart": [
                {
                    "drive": "sdz",
                    "reallocated": 1200,
                    "pending": 8,
                    "offline_uncorrectable": 8,
                }
            ],
            "temperatures": [
                {"bay": 1, "drive": "sda", "temp": 36},
                {"bay": 2, "drive": "sdb", "temp": 38},
            ],
            "bay_mirror": {
                "bays": [
                    {"bay": 1, "installed": True, "pool": "tank", "state": "online"},
                    {"bay": 2, "installed": True, "pool": "tank", "state": "online"},
                    {"bay": 3, "installed": True, "pool": "tank", "state": "fault"},
                ]
            },
            "zfs_activity": {
                "resilver_running": False,
                "status_line": "scan: scrub repaired 0B in 00:03:21 with 0 errors on Thu Nov  5 03:48:39 2026",
            },
        },
        "lifeline": {
            "sessions": [
                {
                    "id": "drive:tank:raidz1-0:wwn:abc:attempt-1",
                    "status": "active",
                    "original_fault": {
                        "bay": 3,
                        "device": "sdz",
                        "pool": "tank",
                        "model": "ST8000NE001-2M71",
                        "serial_last4": "ZZZ9",
                        "capacity_bytes": 8001563222016,
                    },
                    "context": {"acknowledgements": {"backup_state": False}},
                    "last_session": {"can_identify_bay": False},
                }
            ]
        },
        "cargo_bay": {
            "backup": {
                "items": [
                    {
                        "state": "AWAITING",
                        "size_bytes": 4_000_000_000,
                        "current_path": "/mnt/tank/Movies/Movies A-M/Film/Film.mkv",
                    },
                ]
            }
        },
        "sentinel_topology": {
            "datasets": [
                {"name": "tank"},
                {"name": "tank/Movies"},
                {"name": "tank/Shows"},
                {"name": "tank/Applications"},
            ],
            "applications": [
                {"id": "plex", "state": "RUNNING"},
                {"id": "tailscale", "state": "RUNNING"},
            ],
            "relationships": [{"application_id": "plex", "dataset_id": "tank/Movies"}],
        },
        "reliability": {
            "active_incident": {
                "incident_id": "recovery:test",
                "likely_cause": "Pool member faulted",
                "confidence": 0.7,
                "confidence_basis": {"hard_alerts": ["a", "b"]},
            }
        },
    }


def _build_model(payload):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    program = (
        "const api=require(process.argv[1]);"
        "let input='';process.stdin.on('data',c=>input+=c);"
        "process.stdin.on('end',()=>process.stdout.write(JSON.stringify(api.buildModel(JSON.parse(input)))));"
    )
    result = subprocess.run(
        [node, "-e", program, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    return json.loads(result.stdout)


def test_fault_model_speaks_plainly_and_recovers_identity_from_lifeline():
    model = _build_model(_fixture())
    assert model["kind"] == "fault"
    assert model["headline"] == "The hard drive in Bay 3 has failed"
    assert model["identity"] == {
        "title": "Bay 3 · Seagate IronWolf Pro 8 TB",
        "serial": "ZZZ9",
    }
    assert model["wrong"][0].startswith(
        "The drive is wearing out. It has already swapped out 1,200"
    )
    assert "Movies" in model["affects"]["folders"]
    assert model["affects"]["affected"] == [{"name": "Plex", "running": True}]
    assert "Tailscale" in model["affects"]["unaffected"]
    assert any("Nov 5" in item["text"] for item in model["protecting"])
    assert "second drive fails" in model["avoid"]
    assert [bay["bad"] for bay in model["bays"]] == [False, False, True]
    steps = model["steps"]
    assert len(steps) == 8
    assert steps[1]["action"] == {"kind": "ack", "label": "I've checked my backup"}
    assert "Movies A-M" in steps[1]["body"]
    assert steps[3]["action"] is None  # identify LED not permitted yet
    assert not any(step["done"] for step in steps)


def test_rebuild_progress_and_earlier_steps_follow_machine_evidence():
    payload = _fixture()
    payload["storage"]["zfs_activity"].update({"resilver_running": True, "percent": 40})
    payload["storage"]["devices"].append(
        {
            "device": "sdy",
            "physical_bay": 3,
            "present": True,
            "serial_last4": "NEW1",
            "pool": "tank",
            "zfs_state": "ONLINE",
        }
    )
    model = _build_model(payload)
    assert model["headline"] == "Your new Bay 3 drive is being set up"
    assert "40% done" in model["sub"]
    done = [step["done"] for step in model["steps"]]
    assert done == [True, True, True, True, True, True, True, False]
    assert model["steps"][1]["confirmed"] is False  # passed, not machine-confirmed


def test_all_clear_without_active_guidance():
    payload = _fixture()
    payload["operator_guidance"] = []
    payload["health"]["state"] = "NOMINAL"
    model = _build_model(payload)
    assert model["kind"] == "clear"
    assert model["headline"] == "Everything's working"
    assert model["poolNote"] == "tank storage is 90% full"


def test_fault_view_modes_folding_and_placement_contract():
    source = SCRIPT.read_text(encoding="utf-8")
    # The virtual front panel stays first; the view leads the overview.
    assert "overview.prepend(view)" in source
    assert "grid.prepend(view)" not in source
    # Pilot gets the compact card and no Technical details drawer.
    assert '"truepanel:mission-mode"' in source
    assert "function renderPilot(model)" in source
    assert (
        'body[data-mission-mode="pilot"] #ffTechnical{display:none!important}' in source
    )
    # Folding is per incident and kept in this browser only.
    assert 'const FOLD_PREFIX="truepanel-fault-view:"' in source
    assert "data-ff-fold" in source
    # Status lights land on the fault view only for the subsystem it owns.
    assert "pill.dataset.gcHealthTarget!==ui.model.subsystem" in source


def test_pilot_tiles_summarise_the_drive_fault():
    model = _build_model(_fixture())
    assert model["subsystem"] == "storage"
    assert [tile["value"] for tile in model["pilotTiles"]] == [
        "Bay 3",
        "tank",
        "2 of 3 OK",
    ]
    assert model["pilotTiles"][0]["note"] == "IronWolf Pro 8 TB"
