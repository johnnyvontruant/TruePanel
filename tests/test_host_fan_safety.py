from pathlib import Path

from truepanel.host.fan_safety import (
    collect_host_fan_safety,
    format_host_fan_safety,
)


def config(*, enabled=True, channels=None):
    fan_control = {
        "enabled": enabled,
    }

    if channels is not None:
        fan_control["controlled_channels"] = channels

    return {
        "hardware": {
            "fan_control": fan_control,
        }
    }


def controller(tmp_path, modes):
    base = tmp_path / "device"
    base.mkdir()

    for channel, mode in modes.items():
        (base / f"pwm{channel}_enable").write_text(
            f"{mode}\n",
            encoding="utf-8",
        )

    return base


def test_disabled_fan_control_is_safe_and_not_applicable():
    report = collect_host_fan_safety(
        config(enabled=False),
        controller_finder=lambda: (_ for _ in ()).throw(
            AssertionError("controller discovery must not run")
        ),
    )

    assert report.safe is True
    assert report.applicable is False
    assert report.checks == ()


def test_all_controlled_channels_in_automatic_mode_are_safe(tmp_path):
    base = controller(
        tmp_path,
        {
            1: 2,
            2: 2,
        },
    )

    report = collect_host_fan_safety(
        config(channels=[1, 2]),
        controller_path=base,
    )

    assert report.safe is True
    assert [check.channel for check in report.checks] == [1, 2]
    assert [check.mode for check in report.checks] == [2, 2]
    assert all(check.automatic for check in report.checks)

    payload = report.to_dict()
    assert payload["schema_version"] == 1
    assert payload["safe"] is True
    assert payload["applicable"] is True


def test_manual_mode_fails_closed(tmp_path):
    base = controller(
        tmp_path,
        {
            1: 2,
            2: 1,
        },
    )

    report = collect_host_fan_safety(
        config(channels=[1, 2]),
        controller_path=base,
    )

    assert report.safe is False
    assert report.checks[1].mode == 1
    assert report.checks[1].automatic is False
    assert "observed mode 1" in report.checks[1].detail


def test_missing_mode_file_fails_closed(tmp_path):
    base = controller(
        tmp_path,
        {
            1: 2,
        },
    )

    report = collect_host_fan_safety(
        config(channels=[1, 2]),
        controller_path=base,
    )

    assert report.safe is False
    assert report.checks[1].mode is None
    assert report.checks[1].automatic is False


def test_unavailable_controller_fails_closed():
    report = collect_host_fan_safety(
        config(channels=[1, 2]),
        controller_finder=lambda: None,
    )

    assert report.safe is False
    assert report.controller_path is None
    assert report.checks == ()


def test_verifier_reuses_runtime_channel_normalization(tmp_path):
    base = controller(
        tmp_path,
        {
            1: 2,
            2: 2,
        },
    )

    report = collect_host_fan_safety(
        config(channels=[2, "1", 2, 3, "bad"]),
        controller_path=base,
    )

    assert [check.channel for check in report.checks] == [2, 1]
    assert report.safe is True


def test_formatter_reports_automatic_and_review(tmp_path):
    safe_base = controller(
        tmp_path / "safe",
        {
            1: 2,
            2: 2,
        },
    )
    unsafe_base = controller(
        tmp_path / "unsafe",
        {
            1: 2,
            2: 1,
        },
    )

    safe_text = format_host_fan_safety(
        collect_host_fan_safety(
            config(),
            controller_path=safe_base,
        )
    )
    unsafe_text = format_host_fan_safety(
        collect_host_fan_safety(
            config(),
            controller_path=unsafe_base,
        )
    )

    assert "Motherboard fan control: AUTOMATIC" in safe_text
    assert "[PASS] channel 1" in safe_text
    assert "Motherboard fan control: REVIEW" in unsafe_text
    assert "[REVIEW] channel 2" in unsafe_text


def test_fan_safety_module_is_strictly_passive():
    source = Path(
        "truepanel/host/fan_safety.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        ".write_text(",
        ".touch(",
        ".mkdir(",
        ".unlink(",
        "subprocess",
        "request_profile",
        "HostAgentRuntime",
        "FanHardwareExecutor",
        "fan-control.sock",
        "systemctl",
    ):
        assert forbidden not in source
