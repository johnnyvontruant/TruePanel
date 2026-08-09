import json
from datetime import datetime, timezone

from truepanel import __version__
from truepanel.compatibility.models import (
    CompatibilityCheck,
    CompatibilityReport,
)
from truepanel.compatibility.support import (
    PRIVACY_CONTRACT,
    SUPPORT_BUNDLE_SCHEMA_VERSION,
    build_support_bundle,
    default_support_path,
    support_bundle_contains_forbidden_keys,
    write_support_bundle,
)


def make_report():
    return CompatibilityReport(
        classification="SUPPORTED",
        installation_mode="OBSERVATION ONLY",
        hardware_control="LOCKED - COMMISSIONING REQUIRED",
        checks=(
            CompatibilityCheck(
                status="PASS",
                name="Storage Discovery",
                detail="9 whole-disk devices discovered",
            ),
            CompatibilityCheck(
                status="PASS",
                name="Front Panel Serial",
                detail=(
                    "/dev/ttyS1 present; controller was "
                    "not opened or actively probed"
                ),
            ),
        ),
    )


def fixed_time():
    return datetime(
        2026,
        8,
        9,
        22,
        44,
        0,
        tzinfo=timezone.utc,
    )


def test_support_bundle_schema_and_version():
    payload = build_support_bundle(
        make_report(),
        generated_at=fixed_time(),
    )

    assert (
        payload["schema_version"]
        == SUPPORT_BUNDLE_SCHEMA_VERSION
        == 1
    )
    assert payload["truepanel_version"] == __version__
    assert payload["generated_at"] == (
        "2026-08-09T22:44:00+00:00"
    )
    assert payload["privacy"] == PRIVACY_CONTRACT
    assert (
        payload["compatibility"]["classification"]
        == "SUPPORTED"
    )


def test_support_bundle_declares_privacy_exclusions():
    payload = build_support_bundle(
        make_report(),
        generated_at=fixed_time(),
    )

    assert payload["privacy"]["hostname"] == "excluded"
    assert payload["privacy"]["ip_addresses"] == "excluded"
    assert payload["privacy"]["serial_numbers"] == "excluded"
    assert payload["privacy"]["wwids"] == "excluded"
    assert payload["privacy"]["mac_addresses"] == "excluded"
    assert payload["privacy"]["usernames"] == "excluded"
    assert (
        payload["privacy"]["configuration_secrets"]
        == "excluded"
    )


def test_support_bundle_has_no_forbidden_data_fields():
    payload = build_support_bundle(
        make_report(),
        generated_at=fixed_time(),
    )

    assert (
        support_bundle_contains_forbidden_keys(
            payload
        )
        == set()
    )


def test_default_support_filename_is_deterministic():
    path = default_support_path(
        generated_at=fixed_time(),
    )

    assert path.name == (
        "truepanel-support-20260809-224400.json"
    )


def test_write_support_bundle_to_explicit_path(
    tmp_path,
):
    output = tmp_path / "support.json"

    written = write_support_bundle(
        make_report(),
        output=output,
        generated_at=fixed_time(),
    )

    assert written == output
    assert output.is_file()

    payload = json.loads(
        output.read_text()
    )

    assert payload["schema_version"] == 1
    assert (
        payload["compatibility"]["hardware_control"]
        == "LOCKED - COMMISSIONING REQUIRED"
    )


def test_support_bundle_ends_with_newline(
    tmp_path,
):
    output = tmp_path / "support.json"

    write_support_bundle(
        make_report(),
        output=output,
        generated_at=fixed_time(),
    )

    assert output.read_text().endswith("\n")
