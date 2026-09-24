from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ui_source() -> str:
    return (
        ROOT / "truepanel/web/static/wingman.js"
    ).read_text(encoding="utf-8")


def _server_source() -> str:
    return (
        ROOT / "truepanel/web/pathfinder_server.py"
    ).read_text(encoding="utf-8")


def test_wingman_ui_is_explicit_operator_trigger_only():
    source = _ui_source()

    assert 'const BRIEF_URL="/api/v1/wingman/brief";' in source
    assert 'button.addEventListener("click",async()=>{' in source
    assert 'method:"POST"' in source

    assert 'truepanel:status' not in source
    assert "setInterval(" not in source

    assert "INSTRUMENT BRIEF" in source
    assert "CHECK READINESS" in source
    assert "AI BRIEF" in source
    assert "Instrument brief: model free · AI: operator triggered" in source


def test_wingman_ui_preserves_advisory_only_authority():
    source = _ui_source()

    assert "ADVISORY ONLY · CONTROL AUTHORITY FALSE" in source
    assert "payload.control_authority!==false" in source
    assert "payload.production_mutation!==false" in source
    assert "payload.advisory_only!==true" in source
    assert "Mission Control telemetry remains authoritative." in source


def test_wingman_ui_surfaces_grounding_sources():
    source = _ui_source()

    assert "Mission Control Reliability" in source
    assert "summary_source_ids" in source
    assert "item.source_ids" in source
    assert "sourceBadges" in source


def test_pathfinder_serves_and_injects_wingman_ui():
    source = _server_source()

    assert '_WINGMAN_SCRIPT = "wingman.js"' in source
    assert 'b"<!-- truepanel-wingman -->"' in source
    assert 'b\'\\n<script src="/wingman.js" defer></script>\\n\'' in source
    assert 'if parsed.path == f"/{_WINGMAN_SCRIPT}":' in source
    assert "if _WINGMAN_MARKER not in body:" in source


def test_wingman_ui_has_mode_aware_compact_presentation():
    source = _ui_source()

    assert 'data-wingman-state="standby"' in source
    assert 'data-wingman-state="ready"' in source
    assert 'body[data-mission-mode="pilot"]' in source
    assert ".wm-columns" in source
    assert ".wm-uncertainty" in source

    # Flight Engineer is the default/full presentation. Pilot mode
    # applies only narrowing overrides.
    assert 'setWingmanState(view,"standby")' in source
    assert 'setWingmanState(view,"busy")' in source
    assert 'setWingmanState(view,"ready")' in source
    assert 'setWingmanState(view,"hold")' in source


def test_wingman_busy_state_reports_elapsed_time_without_fake_progress():
    source = _ui_source()

    assert "REVIEWING VERIFIED INSTRUMENTS" in source
    assert 'class="wm-elapsed"' in source
    assert "performance.now()" in source
    assert "window.setTimeout(updateElapsed,1000)" in source
    assert "elapsedTimerActive=false" in source

    assert "progress" not in source.lower()
    assert "percent complete" not in source.lower()
    assert "setInterval(" not in source


def test_wingman_sources_have_compact_and_full_presentations():
    source = _ui_source()

    assert '"status:reliability":{' in source
    assert 'full:"Mission Control Reliability"' in source
    assert 'compact:"RELIABILITY"' in source

    assert 'class="wm-source-prefix">SOURCE · ' in source
    assert 'class="wm-source-full"' in source
    assert 'class="wm-source-compact"' in source

    assert 'data-source-id="${esc(sourceId)}"' in source
    assert 'title="${esc(`${label.full} · ${sourceId}`)}"' in source


def test_wingman_pilot_uses_compact_source_badges():
    source = _ui_source()

    assert (
        'body[data-mission-mode="pilot"] '
        '#${VIEW_ID} .wm-source-full'
        in source
    )
    assert (
        'body[data-mission-mode="pilot"] '
        '#${VIEW_ID} .wm-source-compact'
        in source
    )
    assert ".wm-source-compact{" in source


def test_wingman_offline_routes_are_get_only_and_keep_model_optional():
    source = _ui_source()
    assert 'const OFFLINE_URL="/api/v1/wingman/offline-brief";' in source
    assert 'const READINESS_URL="/api/v1/wingman/readiness";' in source
    assert 'offlineButton.addEventListener("click",async()=>{' in source
    assert 'readinessButton.addEventListener("click",async()=>{' in source
    assert 'method:"GET",cache:"no-store"' in source
    assert 'payload.model_invoked===false' in source
    assert 'payload.launch_authorized!==false' in source
    assert 'if(readiness.status!=="READY_FOR_RECHECK"){' in source
    assert 'body.innerHTML="<div class=\'wm-state hold\'>"' in source
    assert 'offlinePanel.innerHTML=offlineMarkup(payload);' in source
    assert 'readinessPanel.innerHTML=readinessMarkup(payload);' in source


def test_pilot_mode_does_not_hide_offline_uncertainty_or_readiness_hold():
    source = _ui_source()
    # Prior CSS hid every uncertainty when an AI brief succeeded, even
    # when a separate offline briefing still needed to display its caveats.
    assert (
        'body[data-mission-mode="pilot"] '
        '#${VIEW_ID}[data-wingman-state="ready"] .wm-body .wm-uncertainty,'
        in source
    )
    assert (
        'body[data-mission-mode="pilot"] '
        '#${VIEW_ID}[data-wingman-state="ready"] .wm-uncertainty,'
        not in source
    )
    assert 'wm-readiness-panel' in source
    assert 'wm-offline-panel' in source



def test_ai_brief_is_primary_and_engineer_details_start_collapsed():
    source = _ui_source()
    assert '<h3>Plain-language system brief</h3>' in source
    assert '<button class="wm-brief wm-ai" type="button">AI BRIEF</button>' in source
    assert '<details class="wm-deep-dive">' in source
    assert '<summary>ENGINEER DETAILS' in source
    assert source.index('<button class="wm-brief wm-ai"') < source.index(
        '<button class="wm-brief wm-offline"'
    )
    assert source.index('<button class="wm-brief wm-offline"') < source.index(
        '<button class="wm-brief wm-readiness"'
    )
    # No model starts when the page is opened; explicit operator action is required.
    assert 'button.addEventListener("click",async()=>{' in source
    assert 'if(deepDive) deepDive.open=true;' in source
    assert (
        'body[data-mission-mode="pilot"] '
        '#${VIEW_ID}[data-wingman-state="standby"] .wm-body,'
        not in source
    )
