import json

import pytest

from truepanel.history.black_box import (
    REDACTED,
    BlackBoxFrame,
    BlackBoxReplay,
    sanitize_black_box_value,
)
from truepanel.history.black_box_api import BlackBoxReplayAPI
from truepanel.history.black_box_chaos import (
    BlackBoxChaosFault,
    BlackBoxChaosScenario,
)
from truepanel.history.black_box_compatibility import CompatibilityReplayProfile
from truepanel.history.black_box_session import BlackBoxReplaySession


def support_bundle(detail: str) -> dict:
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
                    "name": "Network Observation",
                    "detail": detail,
                }
            ],
        },
    }


def test_sanitizer_redacts_ipv6_without_eating_time_like_text():
    sanitized = sanitize_black_box_value(
        {
            "compressed": "peer 2001:db8::42",
            "loopback": "listener [::1]:8787",
            "mapped": "peer ::ffff:192.0.2.44",
            "time": "last sample 12:34:56",
        }
    )

    assert sanitized["compressed"] == f"peer {REDACTED}"
    assert sanitized["loopback"] == f"listener [{REDACTED}]:8787"
    assert sanitized["mapped"] == f"peer {REDACTED}"
    assert sanitized["time"] == "last sample 12:34:56"


def test_frame_capture_redacts_ipv6_in_browser_visible_strings():
    frame = BlackBoxFrame.capture(
        captured_at=1.0,
        sequence=1,
        lcd={"line1": "NAS 2001:db8::10"},
        alerts=[{"severity": "warning", "message": "peer ::1 unavailable"}],
    )

    encoded = json.dumps(frame.as_dict(), sort_keys=True)
    assert "2001:db8::10" not in encoded
    assert "::1" not in encoded
    assert REDACTED in encoded


def test_chaos_and_api_pipeline_keep_ipv6_private():
    replay = BlackBoxReplay(
        (
            BlackBoxFrame.capture(captured_at=1.0, sequence=1),
            BlackBoxFrame.capture(captured_at=2.0, sequence=2),
        )
    )
    scenario = BlackBoxChaosScenario(
        {
            2: BlackBoxChaosFault(
                "storage_degraded",
                {"message": "simulated peer 2001:db8::99"},
            )
        }
    )
    payload = BlackBoxReplayAPI(
        BlackBoxReplaySession(replay, chaos=scenario)
    ).frame(2)

    encoded = json.dumps(payload, sort_keys=True)
    assert "2001:db8::99" not in encoded
    assert REDACTED in encoded


def test_compatibility_replay_rejects_ipv6_requiring_redaction():
    with pytest.raises(ValueError, match="requiring privacy redaction"):
        CompatibilityReplayProfile.from_support_bundle(
            support_bundle("dashboard reachable at 2001:db8::108")
        )
