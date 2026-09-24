"""Presentation-only regression checks for Mission Control cockpit stabilization."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "truepanel" / "web" / "static"
GLASS = ROOT / "glass-cockpit.js"
VARIANTS = ROOT / "cockpit-variants.js"


def test_hottest_drive_uses_its_own_identity_not_incident_bay():
    source = GLASS.read_text(encoding="utf-8")
    assert "function hottestDriveSummary(readings){" in source
    assert "hottestSummary.label" in source
    assert "incidentBay(incident)" not in source[source.index("function render(view,payload){"):source.index("function pathMarkup")]
    assert "storage.temperatures" in source


@pytest.mark.skipif(shutil.which("node") is None, reason="Node unavailable")
def test_hottest_drive_fixtures_without_hardware():
    source = GLASS.read_text(encoding="utf-8")
    start = source.index("function hottestDriveSummary(readings){")
    end = source.index("function render(view,payload){", start)
    helpers = source[start:end]
    fixture = [
        {"drive": "nvme0n1", "bay": None, "temp": 47},
        {"drive": "nvme1n1", "bay": None, "temp": 47},
        {"drive": "sda", "bay": 6, "temp": 43},
        {"drive": "sdc", "bay": 4, "temp": 42},
        {"drive": "sdd", "bay": 3, "temp": 41},
    ]
    script = (
        'const array=v=>Array.isArray(v)?v:[];\n'
        'const first=(...values)=>values.find(v=>v!==undefined&&v!==null&&v!=="");\n'
        'const number=v=>Number.isFinite(Number(v))?Number(v):null;\n'
        + helpers
        + "\nconst fixture=" + json.dumps(fixture) + ";\n"
        + 'const hot=hottestDriveSummary(fixture);\n'
        + 'if(hot.value!==47||hot.label!=="NVMe (nvme0n1), NVMe (nvme1n1)")'
          'throw Error(JSON.stringify(hot));\n'
        + 'const hdd=hottestDriveSummary([{drive:"sda",bay:6,temp:43}]);\n'
        + 'if(hdd.label!=="Bay 6 (sda)")throw Error(JSON.stringify(hdd));\n'
        + 'const unknown=hottestDriveSummary([{drive:"sdz",bay:null,temp:45}]);\n'
        + 'if(unknown.label!=="Drive sdz (bay unverified)")'
          'throw Error(JSON.stringify(unknown));\n'
        + 'const absent=hottestDriveSummary([]);\n'
        + 'if(absent.value!==null||absent.label!=="Drive identity unavailable")'
          'throw Error(JSON.stringify(absent));\n'
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True,
        check=False, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_reorder_moves_existing_dom_nodes_without_mutating_safety():
    source = VARIANTS.read_text(encoding="utf-8")
    assert "function applyStabilizedDeckOrder(){" in source
    assert "grid.prepend(...cards.filter(" in source
    assert "const sentinel=document.getElementById(\"sentinelFlightDirector\")" in source
    assert "const warning=document.getElementById(\"healthAdvisory\")" in source
    assert "commandStatus.appendChild(strip)" in source
    assert "cpuSlot.append(cpu,load)" in source
    assert "ramSlot.appendChild(ram)" in source
    assert "window.requestAnimationFrame(applyStabilizedDeckOrder)" in source
    assert "fan_runtime" not in source[source.index("function applyStabilizedDeckOrder(){"):source.index("function installVariantSwitcher(){")]
