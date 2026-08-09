from pathlib import Path


INSTALLATION = Path("docs/INSTALLATION.md")
CLI = Path("docs/CLI.md")


def read(path):
    return path.read_text(
        encoding="utf-8"
    )


def test_installation_requires_preinstall_survey():
    text = read(INSTALLATION)

    assert (
        "## Compatibility check before installation"
        in text
    )
    assert (
        "python3 truepanel.py compatibility"
        in text
    )
    assert (
        "Unknown or unverified hardware"
        in text
    )


def test_installation_preserves_control_boundary():
    text = read(INSTALLATION)

    assert (
        "does not authorize fan, LCD, LED, or other "
        "active hardware control"
        in text
    )
    assert (
        "Hardware control remains locked"
        in text
    )


def test_installation_documents_support_bundle():
    text = read(INSTALLATION)

    assert "--support-bundle" in text
    assert "--output truepanel-support.json" in text
    assert "privacy-safe support bundle" in text


def test_cli_documents_all_compatibility_modes():
    text = read(CLI)

    assert "truepanel compatibility" in text
    assert "truepanel compatibility --json" in text
    assert (
        "truepanel compatibility --support-bundle"
        in text
    )
    assert (
        "truepanel compatibility --support-bundle "
        "--output <path>"
        in text
    )


def test_cli_documents_compatibility_states():
    text = read(CLI)

    for state in (
        "`SUPPORTED`",
        "`PARTIAL`",
        "`REVIEW`",
        "`UNSUPPORTED`",
    ):
        assert state in text


def test_cli_documents_passive_safety_contract():
    text = read(CLI)

    assert (
        "The survey is passive."
        in text
    )
    assert (
        "Hardware control remains locked"
        in text
    )


def test_cli_documents_support_bundle_privacy():
    text = read(CLI)

    for excluded in (
        "hostnames",
        "IP addresses",
        "drive serial numbers",
        "WWIDs",
        "MAC addresses",
        "usernames",
        "configuration secrets",
        "pool contents",
    ):
        assert excluded in text
