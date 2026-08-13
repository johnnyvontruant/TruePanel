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


def test_runbook_rehearses_uninstall_and_install_before_mutation():
    text = read(RUNBOOK)

    phase_2 = text.index("## Phase 2: Clean uninstall")
    phase_3 = text.index("## Phase 3: Prove known residue is gone")
    uninstall = text[phase_2:phase_3]

    phase_4 = text.index("## Phase 4: Fresh install")
    phase_5 = text.index("## Phase 5: Immediate post-install verification")
    install = text[phase_4:phase_5]

    assert "bash uninstall.sh" in uninstall
    assert "--dry-run" in uninstall
    assert uninstall.index("--dry-run") < uninstall.index("sudo bash uninstall.sh")
    assert "no services were stopped" in uninstall
    assert "no fan state changed" in uninstall
    assert "no files were removed" in uninstall

    assert "bash install.sh" in install
    assert "--dry-run" in install
    assert install.index("--dry-run") < install.index("sudo bash install.sh")
    assert "no directories were created" in install
    assert "no files were copied or written" in install
    assert "no dependencies were installed" in install
    assert "no services were changed" in install


def test_runbook_preserves_known_good_config_outside_install_root():
    text = read(RUNBOOK)

    baseline = text.index(
        "## Phase 1: Capture the known-good baseline"
    )
    uninstall = text.index(
        "## Phase 2: Clean uninstall"
    )
    block = text[baseline:uninstall]

    assert "TRUEPANEL_VALIDATION_ARTIFACTS" in text
    assert "TruePanel-clean-install-artifacts" in text
    assert (
        "truepanel.yaml.before-clean-install"
        in block
    )
    assert (
        "truepanel-mission-control.env.before-clean-install"
        in block
    )
    assert "sudo cp -a" in block
    assert (
        'test "$TRUEPANEL_VALIDATION_ARTIFACTS" != '
        '/mnt/POOL/DATASET/TruePanel'
        in block
    )


def test_runbook_does_not_use_preserved_config_to_mask_fresh_install():
    text = read(RUNBOOK)

    assert (
        "Do not restore them during the fresh-install acceptance phases"
        in text
    )
    assert (
        "never copy them into the fresh installation merely to make "
        "acceptance pass"
        in text
    )

    phase_4 = text.index(
        "## Phase 4: Fresh install"
    )
    phase_7 = text.index(
        "## Phase 7: Reboot validation"
    )
    fresh_acceptance = text[phase_4:phase_7]

    assert "truepanel.yaml.before-clean-install" not in fresh_acceptance


def test_runbook_persists_before_and_after_support_bundles():
    text = read(RUNBOOK)

    assert (
        '$TRUEPANEL_VALIDATION_ARTIFACTS/'
        'truepanel-pre-clean-install.json'
        in text
    )
    assert (
        '$TRUEPANEL_VALIDATION_ARTIFACTS/'
        'truepanel-post-clean-install.json'
        in text
    )
    assert text.count("--support-bundle") >= 2
    assert text.count("sudo test -f") >= 3
    assert (
        "Do not place either bundle inside the managed TruePanel tree."
        in text
    )


def test_pre_clean_support_bundle_is_captured_before_uninstall():
    text = read(RUNBOOK)
    baseline = text.index(
        "truepanel-pre-clean-install.json"
    )
    uninstall = text.index(
        "## Phase 2: Clean uninstall"
    )

    assert baseline < uninstall


def test_post_clean_support_bundle_is_captured_after_acceptance():
    text = read(RUNBOOK)
    phase_5 = text.index(
        "## Phase 5: Immediate post-install verification"
    )
    phase_6 = text.index(
        "## Phase 6: Functional application checks"
    )
    block = text[phase_5:phase_6]

    assert "Host acceptance: PASS" in block
    assert "truepanel-post-clean-install.json" in block
