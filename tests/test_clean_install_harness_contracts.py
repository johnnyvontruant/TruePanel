from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_installer_completion_banner_is_canonical():
    installer = (ROOT / "install.sh").read_text(
        encoding="utf-8",
    )

    assert "TruePanel Install Complete" in installer
    assert "TruePanel installation complete." not in installer


def test_operational_verifier_follows_service_activation():
    runbook = (
        ROOT / "docs" / "CLEAN_INSTALL_VALIDATION.md"
    ).read_text(
        encoding="utf-8",
    )

    lcd = runbook.index(
        "sudo systemctl enable --now truepanel.service"
    )

    mission_control = runbook.index(
        "sudo systemctl enable --now "
        "truepanel-mission-control.service"
    )

    phase5 = runbook.index(
        "## Phase 5: Immediate post-install verification"
    )

    verifier = runbook.index(
        "sudo ./bin/truepanel verify",
        phase5,
    )

    assert lcd < verifier
    assert mission_control < verifier
    assert "operational verifier" in runbook


def test_runbook_documents_nested_reader_schema():
    runbook = (
        ROOT / "docs" / "CLEAN_INSTALL_VALIDATION.md"
    ).read_text(
        encoding="utf-8",
    )

    assert "payload[\"reader\"][\"connected\"]" in runbook
    assert "payload[\"reader\"][\"button_reports\"]" in runbook


def test_run3_release_evidence_records_graduation():
    evidence = (
        ROOT / "docs" / "CLEAN_INSTALL_RUN3_RESULTS.md"
    ).read_text(
        encoding="utf-8",
    )

    assert "RUN 3 CLEAN INSTALL GRADUATION = PASS" in evidence
    assert "pre-fix generation: **5**" in evidence
    assert "corrected fresh startup: **0**" in evidence
    assert "full reboot: **0**" in evidence
    assert "AUTOMATIC" in evidence
    assert "Host acceptance: **PASS**" in evidence
