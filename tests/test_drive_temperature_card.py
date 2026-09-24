"""Regression for the existing Mission Control temperature card renderer.

Runs a synthetic status fixture through its actual JavaScript helper when Node
is available. No NAS, disk, browser, hardware, or model dependencies.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = (
    Path(__file__).resolve().parents[1]
    / "truepanel"
    / "web"
    / "static"
    / "index.html"
)


def test_temperature_card_uses_drive_identity_renderer():
    html = PAGE.read_text(encoding="utf-8")
    assert 'q("temps").innerHTML=driveTemperatureRows(st.temperatures)' in html
    assert "function driveTemperatureLabel(reading)" in html
    assert "function driveTemperatureRows(readings)" in html


def test_temperature_card_preserves_reported_identity_and_unknown_bays():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node not available for JavaScript renderer fixture")

    html = PAGE.read_text(encoding="utf-8")
    start = html.index("function driveTemperatureLabel(reading){")
    end = html.index("function render(data){", start)
    helpers = html[start:end]
    readings = [
        {"drive": "nvme0n1", "bay": None, "temp": 47},
        {"drive": "nvme1n1", "bay": None, "temp": 47},
        {"drive": "sda", "bay": 6, "temp": 43},
        {"drive": "sdc", "bay": 4, "temp": 42},
        {"drive": "sde", "bay": 5, "temp": 42},
        {"drive": "sdb", "bay": 1, "temp": 41},
        {"drive": "sdg", "bay": 2, "temp": 41},
    ]
    script = (
        'const rows=(items,fn)=>Array.isArray(items)&&items.length'
        '?items.map(fn).join(""):"No telemetry available";\n'
        + helpers
        + "\nconst readings="
        + json.dumps(readings)
        + ";\n"
        + "const labels=readings.map(driveTemperatureLabel);\n"
        + "const html=driveTemperatureRows(readings);\n"
        + 'if(labels.join("|")!=="NVMe · nvme0n1|NVMe · nvme1n1|'
        'Bay 6 · sda|Bay 4 · sdc|Bay 5 · sde|Bay 1 · sdb|Bay 2 · sdg")'
        'throw Error(JSON.stringify(labels));\n'
        + 'if(html.includes("Bay 3"))throw Error("Invented a missing drive");\n'
        + 'if(!html.includes("Bay 6 · sda")||!html.includes("43°C"))'
        'throw Error("Missing drive identity or temperature");\n'
        + 'const unknown=driveTemperatureRows([{drive:"sdz",bay:null,temp:39}]);\n'
        + 'if(!unknown.includes("Drive · sdz (bay unknown)"))'
        'throw Error("Invented an unknown bay");\n'
        + 'const unsafe=driveTemperatureRows([{drive:"<img onerror=alert(1)>",temp:null}]);\n'
        + 'if(unsafe.includes("<img")||!unsafe.includes("&lt;img")'
        '||!unsafe.includes("Temperature unavailable"))'
        'throw Error("Unsafe label or missing temperature fallback");\n'
    )
    completed = subprocess.run(
        [node, "-e", script],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
