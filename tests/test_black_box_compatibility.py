import copy
import json

import pytest

from truepanel.history.black_box_compatibility import (
    COMPATIBILITY_REPLAY_SCHEMA_VERSION,
    MAX_SUPPORT_BUNDLE_BYTES,
    CompatibilityReplayProfile,
    load_compatibility_replay_profile,
)


def support_bundle():
    return {
        "schema_version": 1,
        "truepanel_version": "1.2.0rc1",
        "generated_at": "2026-08-14T01:00:00+00:00",
        "privacy": {
            "hostname": "excluded",
            "ip_addresses": "excluded",
            "serial_numbers": "excluded",
            "wwids": "excluded",
            "mac_addresses": "excluded",
            "usernames": "excluded",
            "configuration_secrets": "excluded",
            "pool_contents": "excluded",
        },
        "compatibility": {
            "classification": "SUPPORTED",
            "installation_mode": "OBSERVATION ONLY",
            "hardware_control": "LOCKED - COMMISSIONING REQUIRED",
            "checks": [
                {
                    "status": "PASS",
                    "name": "Storage Discovery",
                    "detail": "9 whole-disk devices discovered",
                },
                {
                    "status": "REVIEW",
                    "name": "Front Panel Serial",
                    "detail": (
                        "/dev/ttyS1 present; controller was not opened"
                    ),
                },
            ],
        },
    }


def test_compatibility_replay_profile_is_deterministic_and_non_mutating():
    payload = support_bundle()
    before = copy.deepcopy(payload)

    profile = CompatibilityReplayProfile.from_support_bundle(payload)

    assert payload == before
    assert profile.replay_schema_version == (
        COMPATIBILITY_REPLAY_SCHEMA_VERSION
    )
    assert profile.source_schema_version == 1
    assert profile.source_truepanel_version == "1.2.0rc1"
    assert profile.classification == "SUPPORTED"
    assert profile.simulation_only is True
    assert profile.privacy == "verified-support-bundle"
    assert profile.status_counts == {"PASS": 1, "REVIEW": 1}


def test_compatibility_replay_rejects_unknown_or_weakened_schema():
    payload = support_bundle()
    payload["schema_version"] = 2

    with pytest.raises(
        ValueError,
        match="unsupported compatibility support bundle schema",
    ):
        CompatibilityReplayProfile.from_support_bundle(payload)

    payload = support_bundle()
    payload["compatibility"]["device_model"] = "unknown"

    with pytest.raises(ValueError, match="fields do not match schema"):
        CompatibilityReplayProfile.from_support_bundle(payload)


def test_compatibility_replay_requires_full_privacy_contract():
    payload = support_bundle()
    payload["privacy"]["hostname"] = "included"

    with pytest.raises(ValueError, match="privacy contract"):
        CompatibilityReplayProfile.from_support_bundle(payload)


def test_compatibility_replay_rejects_payload_requiring_redaction():
    payload = support_bundle()
    payload["compatibility"]["checks"][0]["detail"] = (
        "dashboard reachable at 192.168.0.108"
    )

    with pytest.raises(ValueError, match="requiring privacy redaction"):
        CompatibilityReplayProfile.from_support_bundle(payload)


def test_compatibility_replay_seed_frame_is_simulation_only():
    profile = CompatibilityReplayProfile.from_support_bundle(
        support_bundle()
    )

    frame = profile.to_black_box_frame(
        captured_at=42.5,
        sequence=7,
    )

    assert frame.captured_at == 42.5
    assert frame.sequence == 7
    assert frame.lcd == {}
    assert frame.fan == {}
    assert frame.storage == {}
    assert frame.buttons == {}
    assert frame.alerts == []
    assert (
        frame.telemetry["compatibility_replay"]["classification"]
        == "SUPPORTED"
    )
    assert (
        frame.mission_control["compatibility_replay"]["source"]
        == "support_bundle"
    )
    assert (
        frame.mission_control["compatibility_replay"]["simulation_only"]
        is True
    )


def test_load_compatibility_replay_profile_from_bounded_json(tmp_path):
    path = tmp_path / "support.json"
    path.write_text(
        json.dumps(support_bundle()),
        encoding="utf-8",
    )

    profile = load_compatibility_replay_profile(path)

    assert profile.classification == "SUPPORTED"
    assert profile.status_counts == {"PASS": 1, "REVIEW": 1}

    oversized = tmp_path / "oversized.json"
    oversized.write_text(
        "x" * (MAX_SUPPORT_BUNDLE_BYTES + 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exceeds maximum size"):
        load_compatibility_replay_profile(oversized)
