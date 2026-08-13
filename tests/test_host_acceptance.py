from truepanel.host.acceptance import (
    build_host_acceptance_report,
    format_host_acceptance_report,
)
from truepanel.host.fan_safety import (
    FanAutomaticCheck,
    HostFanSafetyReport,
)
from truepanel.host.readiness import (
    HostReadinessCheck,
    HostReadinessReport,
)


def readiness(*, prepared=True):
    return HostReadinessReport(
        root="/",
        checks=(
            HostReadinessCheck(
                "python_activation_locked",
                True,
                "locked",
            ),
            HostReadinessCheck(
                "deployment_safe",
                prepared,
                "safe" if prepared else "review",
            ),
        ),
    )


def fan_safety(*, safe=True):
    return HostFanSafetyReport(
        fan_control_enabled=True,
        controller_path="/sys/class/hwmon/hwmon10/device",
        checks=(
            FanAutomaticCheck(
                channel=1,
                path="/sys/class/hwmon/hwmon10/device/pwm1_enable",
                mode=2 if safe else 1,
                automatic=safe,
                detail="automatic" if safe else "manual",
            ),
        ),
        reason="safe" if safe else "review",
    )


def test_acceptance_requires_readiness_and_fan_safety():
    assert build_host_acceptance_report(
        readiness(),
        fan_safety(),
    ).accepted is True

    assert build_host_acceptance_report(
        readiness(prepared=False),
        fan_safety(),
    ).accepted is False

    assert build_host_acceptance_report(
        readiness(),
        fan_safety(safe=False),
    ).accepted is False


def test_acceptance_json_preserves_underlying_reports():
    report = build_host_acceptance_report(
        readiness(),
        fan_safety(),
    )
    payload = report.to_dict()

    assert payload["schema_version"] == 1
    assert payload["accepted"] is True
    assert payload["activation_state"] == "locked"
    assert payload["readiness"]["prepared_safely"] is True
    assert payload["fan_safety"]["safe"] is True


def test_acceptance_formatter_surfaces_final_verdict():
    accepted = format_host_acceptance_report(
        build_host_acceptance_report(
            readiness(),
            fan_safety(),
        )
    )
    review = format_host_acceptance_report(
        build_host_acceptance_report(
            readiness(),
            fan_safety(safe=False),
        )
    )

    assert "Host acceptance: PASS" in accepted
    assert "Dormant Host readiness: PREPARED SAFELY" in accepted
    assert "Motherboard fan control: AUTOMATIC" in accepted
    assert "Standalone activation: LOCKED" in accepted
    assert "Host acceptance: REVIEW" in review


def test_acceptance_report_is_aggregation_only():
    from pathlib import Path

    source = Path(
        "truepanel/host/acceptance.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "subprocess",
        "systemctl",
        ".write_text(",
        ".touch(",
        ".mkdir(",
        ".unlink(",
        "HostOwnershipGuard",
        "request_profile(",
    ):
        assert forbidden not in source
