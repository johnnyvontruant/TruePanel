from pathlib import Path

from truepanel.web import server


def test_lifeline_assets_exist_and_are_served():
    cockpit = server.STATIC_DIR / "lifeline.js"
    actions = server.STATIC_DIR / "lifeline-actions.js"
    assert cockpit.is_file()
    assert actions.is_file()

    source = Path(server.__file__).read_text(encoding="utf-8")
    assert '"/lifeline.js"' in source
    assert '"/lifeline-actions.js"' in source
    assert "truepanel-lifeline" in source
    assert "truepanel-lifeline-actions" in source


def test_lifeline_cockpit_consumes_only_status_api():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert 'STATUS_URL="/api/v1/status"' in source
    assert "repair_session" in source
    assert "PLANNING ONLY" in source
    assert "Storage write authority locked" in source
    assert "Persistent repair sessions" in source

    forbidden = (
        'method:"POST"',
        'method:"PUT"',
        'method:"PATCH"',
        'method:"DELETE"',
        "/api/v1/pool",
        "/api/v1/storage/replace",
        "zpool replace",
        "zpool offline",
    )
    for token in forbidden:
        assert token not in source


def test_lifeline_actions_only_post_metadata_acknowledgement():
    source = (server.STATIC_DIR / "lifeline-actions.js").read_text(
        encoding="utf-8"
    )

    assert 'ACK_URL="/api/v1/lifeline/acknowledge"' in source
    assert 'method:"POST"' in source
    assert '"X-TruePanel-Intent":"lifeline-backup-ack"' in source
    assert "ACKNOWLEDGE_BACKUP_STATE" in source
    assert 'acknowledgement:"backup_state"' in source

    forbidden = (
        "/api/v1/pool",
        "/api/v1/storage/replace",
        "/api/v1/fans/profile",
        "/api/v1/lcd/button",
        "zpool replace",
        "zpool offline",
        "force:true",
    )
    for token in forbidden:
        assert token not in source


def test_server_acknowledgement_endpoint_is_confirmation_guarded():
    source = Path(server.__file__).read_text(encoding="utf-8")

    assert '"/api/v1/lifeline/acknowledge"' in source
    assert '"lifeline-backup-ack"' in source
    assert '"ACKNOWLEDGE_BACKUP_STATE"' in source
    assert 'acknowledgement != "backup_state"' in source
    assert '"hardware_mutation": False' in source


def test_lifeline_renders_repair_prerequisites_and_replacement_validation():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert "Repair prerequisites" in source
    assert "Replacement candidate valid" in source
    assert "Replacement candidate blocked" in source
    assert "Recovery verification samples" in source
    assert "REPAIR VERIFIED" in source
    assert "can_execute_replacement" in source


def test_checklist_owns_primary_active_recovery_presentation():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert "CHECKLIST is the primary current-recovery presentation" in source
    assert "if(checklistCodes.has(code)||renderedFallback.has(code)) continue" in source
    assert "Active recovery is presented once in Project CHECKLIST above." in source
    assert "The ledger keeps identity and progress without opening another full recovery card." in source


def test_lifeline_ledger_deduplicates_by_persistent_session_identity():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert "function ledgerIdentity(item)" in source
    assert 'if(item&&item.id) return `id:${item.id}`' in source
    assert "function dedupeLedger(items)" in source
    assert "const ledger=dedupeLedger" in source
    assert 'data-lifeline-session-id=' in source


def test_repair_ledger_uses_compact_rows_instead_of_reopening_full_cards():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert "function ledgerRow(item)" in source
    assert 'class="ll-ledger-row' in source
    assert "Recent repair history" in source
    assert "active.map(ledgerRow)" in source
    assert "recentCompleted.map(ledgerRow)" in source
    assert "[...active,...completed.slice(-3)]" not in source
    assert "visible.map(item=>item&&item.last_session?sessionCard" not in source


def test_lifeline_python_session_has_no_subprocess_or_storage_write_client():
    session = Path("truepanel/lifeline/session.py").read_text(encoding="utf-8")
    store = Path("truepanel/lifeline/store.py").read_text(encoding="utf-8")

    for source in (session, store):
        assert "subprocess" not in source
        assert "pool.replace" not in source
        assert "zpool" not in source
        assert "requests." not in source
