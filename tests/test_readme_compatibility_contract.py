from pathlib import Path


README = Path("README.md")


def readme_text():
    return README.read_text(
        encoding="utf-8"
    )


def test_readme_documents_preinstall_compatibility():
    text = readme_text()

    assert (
        "## Check compatibility before installation"
        in text
    )
    assert (
        "python3 truepanel.py compatibility"
        in text
    )
    assert (
        "before TruePanel is installed"
        in text
    )


def test_readme_documents_compatibility_states():
    text = readme_text()

    for state in (
        "`SUPPORTED`",
        "`PARTIAL`",
        "`REVIEW`",
        "`UNSUPPORTED`",
    ):
        assert state in text


def test_readme_keeps_hardware_authority_separate():
    text = readme_text()

    assert (
        "does **not** authorize active fan, LED, LCD, "
        "or other hardware control"
    ) in text

    assert (
        "Hardware control remains locked"
        in text
    )


def test_readme_documents_support_bundle():
    text = readme_text()

    assert "--support-bundle" in text
    assert "--output truepanel-support.json" in text
    assert "privacy-safe support bundle" in text


def test_readme_documents_support_bundle_privacy():
    text = readme_text()

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
