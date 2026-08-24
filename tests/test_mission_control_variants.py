from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "truepanel"
    / "web"
    / "static"
    / "cockpit-variants.js"
)


def text():
    return SCRIPT.read_text(encoding="utf-8")


def test_variant_layer_uses_read_only_status_get_only():
    script = text()

    assert 'const STATUS_URL="/api/v1/status"' in script
    assert "fetch(STATUS_URL" in script
    assert 'method:"POST"' not in script
    assert 'method:"PUT"' not in script
    assert 'method:"PATCH"' not in script
    assert 'method:"DELETE"' not in script
    assert "XMLHttpRequest" not in script
    assert "/api/v1/fans/profile" not in script
    assert "/api/v1/lcd/button" not in script
    assert "/api/v1/lifeline/identify" not in script


def test_lcd_is_rendered_as_a125_style_five_by_seven_character_cells():
    script = text()

    assert 'grid-template-columns:repeat(5,1fr)' in script
    assert 'grid-template-rows:repeat(7,1fr)' in script
    assert 'grid-template-columns:repeat(16,minmax(0,1fr))' in script
    assert 'document.getElementById("virtualLcdLine1")' in script
    assert 'document.getElementById("virtualLcdLine2")' in script
    assert 'document.getElementById("cockpitLcdMatrix")' in script
    assert 'row1.replaceChildren(renderMatrixLine(next1))' in script
    assert 'row2.replaceChildren(renderMatrixLine(next2))' in script
    assert 'if(next1!==previous1)' in script
    assert 'if(next2!==previous2)' in script


def test_matrix_observers_do_not_mutate_the_source_lcd_text_nodes():
    script = text()

    start = script.index("function installMatrixLcd(){")
    end = script.index("function installBayStrip(){")
    matrix = script[start:end]

    assert "new MutationObserver(refresh).observe(line1" in matrix
    assert "new MutationObserver(refresh).observe(line2" in matrix
    assert "line1.textContent=" not in matrix
    assert "line2.textContent=" not in matrix
    assert "line1.className=" not in matrix
    assert "line2.className=" not in matrix


def test_drive_bay_mirror_renders_six_chassis_positions_and_unknown_fails_closed():
    script = text()

    assert 'strip.id="cockpitBayStrip"' in script
    assert 'for(let number=1;number<=6;number+=1)' in script
    assert 'const mirror=data?.storage?.bay_mirror||{}' in script
    assert 'const state=String(record.state||"unknown")' in script
    assert 'Bay identity unavailable · no inference' in script
    assert '.cockpit-bay-led.online' in script
    assert '.cockpit-bay-led.attention' in script
    assert '.cockpit-bay-led.fault' in script
    assert '.cockpit-bay-led.missing' in script
    assert '.cockpit-bay-led.identify' in script


def test_drive_bay_ui_never_renders_private_disk_identity_fields():
    script = text()

    start = script.index("function updateBayStrip(data){")
    end = script.index("function poolPercent(pool){")
    bay_ui = script[start:end]

    for forbidden in (
        "serial",
        "wwn",
        "wwid",
        "partuuid",
        "capacity_bytes",
        "device_path",
    ):
        assert forbidden not in bay_ui


def test_storage_pools_are_compact_health_and_capacity_instruments():
    script = text()

    assert 'class="cockpit-pool-grid"' in script
    assert 'class="cockpit-pool-health ${poolTone(health)}"' in script
    assert 'class="cockpit-pool-meter"' in script
    assert 'class="cockpit-pool-fill"' in script
    assert '`${Math.round(percent)}% used`' in script
    assert '${esc(used)} / ${esc(size)} · ${esc(free)} free' in script
    assert 'String(raw??"").replace("%","")' in script


def test_three_layout_variants_share_one_code_path():
    script = text()

    assert 'function applyLayout(rawMode)' in script
    assert '["a","b","c"].includes' in script
    assert 'A · Current' in script
    assert 'B · LCD Near Top' in script
    assert 'C · LCD First' in script
    assert 'document.body.dataset.cockpitVariant=mode' in script
    assert 'if(mode==="b")' in script
    assert 'else if(mode==="c")' in script
    assert 'else{' in script


def test_variant_b_places_vfp_before_separate_preflight_dock():
    script = text()

    start = script.index('if(mode==="b"){')
    end = script.index('}else if(mode==="c"){')
    variant_b = script[start:end]

    assert "dock.appendChild(preflight)" in variant_b
    assert "grid.prepend(overview)" in variant_b
    assert "grid.insertBefore(vfp,overview.nextSibling)" in variant_b
    assert "grid.insertBefore(dock,vfp.nextSibling)" in variant_b


def test_variant_c_places_vfp_first_then_command_status():
    script = text()

    start = script.index('}else if(mode==="c"){')
    end = script.index('}else{', start)
    variant_c = script[start:end]

    assert "commandRow.append(health,preflight)" in variant_c
    assert "grid.prepend(vfp)" in variant_c
    assert "grid.insertBefore(overview,vfp.nextSibling)" in variant_c


def test_layout_switcher_is_preview_only_and_uses_local_history_state():
    script = text()

    assert 'params.get("cockpit-preview")==="1"||params.has("layout")' in script
    assert 'window.history.replaceState({},"",url)' in script
    assert 'url.searchParams.set("layout",mode)' in script
    assert 'url.searchParams.set("cockpit-preview","1")' in script
