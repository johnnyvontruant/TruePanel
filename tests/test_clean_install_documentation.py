from pathlib import Path


RUNBOOK = Path(
    "docs/CLEAN_INSTALL_VALIDATION.md"
)
INSTALLATION = Path(
    "docs/INSTALLATION.md"
)


def read(path):
    return path.read_text(
        encoding="utf-8"
    )


def test_clean_install_runbook_is_present_and_fail_closed():
    text = read(RUNBOOK)

    assert "# TruePanel Clean-Install Validation Runbook" in text
    assert (
        "Do not repair the installed tree by hand"
        in text
    )
    assert (
        "Do not create "
        "`/run/truepanel/standalone-host-agent.enabled`"
        in text
    )
    assert (
        "If uninstall reports that motherboard Automatic mode "
        "cannot be confirmed, stop."
        in text
    )


def test_runbook_records_baseline_before_uninstall():
    text = read(RUNBOOK)

    baseline = text.index(
        "## Phase 1: Capture the known-good baseline"
    )
    uninstall = text.index(
        "## Phase 2: Clean uninstall"
    )

    assert baseline < uninstall
    assert "./bin/truepanel verify" in text[baseline:uninstall]
    assert "./bin/truepanel compatibility" in text[baseline:uninstall]
    assert "./bin/truepanel host readiness" in text[baseline:uninstall]
    assert "./bin/truepanel host fan-safety" in text[baseline:uninstall]
    assert "./bin/truepanel host cutover-plan" in text[baseline:uninstall]


def test_runbook_proves_known_runtime_residue_is_removed():
    text = read(RUNBOOK)

    for path in (
        "/run/truepanel/standalone-host-agent.enabled",
        "/run/truepanel/host-owner.lock",
        "/run/truepanel/fan-control.sock",
        "/run/truepanel/fan-control-status.json",
        "/run/truepanel/lcd-command.sock",
        "/run/truepanel/lcd-reader-status.json",
        "/run/truepanel/lcd-display-status.json",
    ):
        assert f"test ! -e {path}" in text

    for unit in (
        "truepanel.service",
        "truepanel-mission-control.service",
        "truepanel-host-agent.service",
    ):
        assert f"systemctl cat {unit}" in text


def test_runbook_starts_only_application_services_after_install():
    text = read(RUNBOOK)

    assert (
        "systemctl enable --now truepanel.service"
        in text
    )
    assert (
        "systemctl enable --now truepanel-mission-control.service"
        in text
    )
    assert (
        "Do not enable or start `truepanel-host-agent.service`"
        in text
    )
    assert (
        "ConditionPathExists=/run/truepanel/"
        "standalone-host-agent.enabled"
        in text
    )


def test_runbook_requires_post_install_and_post_reboot_safety_checks():
    text = read(RUNBOOK)

    post_install = text.index(
        "## Phase 5: Immediate post-install verification"
    )
    functional = text.index(
        "## Phase 6: Functional application checks"
    )
    reboot = text.index(
        "## Phase 7: Reboot validation"
    )

    immediate = text[post_install:functional]
    after_reboot = text[reboot:]

    for command in (
        "./bin/truepanel verify",
        "./bin/truepanel host readiness",
        "./bin/truepanel host fan-safety",
    ):
        assert command in immediate
        assert command in after_reboot

    assert (
        "`truepanel-host-agent.service` remains inactive"
        in text
    )


def test_runbook_keeps_cutover_execution_disabled():
    text = read(RUNBOOK)

    assert "Cutover execution: DISABLED" in text
    assert (
        "The standalone Host Agent remains activation-locked"
        in text
    )


def test_installation_guide_links_clean_install_runbook():
    text = read(INSTALLATION)

    assert "CLEAN_INSTALL_VALIDATION.md" in text
    assert "host fan-safety" in text
    assert "host cutover-plan" in text

def test_clean_install_runbook_uses_host_acceptance_gate():
    text = read(RUNBOOK)

    assert text.count("host acceptance") >= 4
    assert "Host acceptance: PASS" in text
    assert "Host acceptance result" in text
