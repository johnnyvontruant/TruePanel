from pathlib import Path

import pytest

from truepanel.hardware.fan_control import (
    FanControlDecision,
    FanProfile,
)
from truepanel.hardware.fan_executor import (
    FanHardwareExecutor,
)


def create_fake_sysfs(
    base: Path,
) -> Path:
    base.mkdir()

    values = {
        "pwm1": "194",
        "pwm1_enable": "2",
        "pwm2": "194",
        "pwm2_enable": "2",
        "pwm3": "194",
        "pwm3_enable": "2",
    }

    for name, value in values.items():
        (
            base
            / name
        ).write_text(
            value
        )

    return base


def read_value(
    base: Path,
    name: str,
) -> int:
    return int(
        (
            base
            / name
        ).read_text()
    )


def manual_decision(
    profile=FanProfile.BALANCED,
    pwm=194,
):
    return FanControlDecision(
        accepted=True,
        requested_profile=profile,
        effective_profile=profile,
        pwm=pwm,
        reason="test",
    )


def automatic_decision():
    return FanControlDecision(
        accepted=True,
        requested_profile=FanProfile.AUTOMATIC,
        effective_profile=FanProfile.AUTOMATIC,
        pwm=None,
        reason="test",
        force_automatic=True,
    )


def afterburners_decision(
    *,
    accepted=True,
):
    return FanControlDecision(
        accepted=accepted,
        requested_profile=FanProfile.QUIET,
        effective_profile=FanProfile.AFTERBURNERS,
        pwm=255,
        reason="test safety override",
    )


def test_executor_captures_original_state(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    executor = FanHardwareExecutor(
        base
    )

    snapshot = executor.snapshot()

    assert snapshot[1].pwm == 194
    assert snapshot[1].mode == 2
    assert snapshot[2].pwm == 194
    assert snapshot[2].mode == 2


def test_manual_profile_controls_only_channels_one_and_two(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    executor = FanHardwareExecutor(
        base
    )

    executor.apply(
        manual_decision(
            profile=FanProfile.COOLING_BOOST,
            pwm=225,
        )
    )

    assert read_value(
        base,
        "pwm1",
    ) == 225
    assert read_value(
        base,
        "pwm2",
    ) == 225
    assert read_value(
        base,
        "pwm1_enable",
    ) == 1
    assert read_value(
        base,
        "pwm2_enable",
    ) == 1

    # Fan 3 is outside the verified control surface.
    assert read_value(
        base,
        "pwm3",
    ) == 194
    assert read_value(
        base,
        "pwm3_enable",
    ) == 2


def test_automatic_decision_restores_mode(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    executor = FanHardwareExecutor(
        base
    )

    executor.apply(
        manual_decision(
            pwm=225
        )
    )
    executor.apply(
        automatic_decision()
    )

    assert read_value(
        base,
        "pwm1_enable",
    ) == 2
    assert read_value(
        base,
        "pwm2_enable",
    ) == 2


def test_afterburners_applies_full_pwm(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    executor = FanHardwareExecutor(
        base
    )

    executor.apply(
        afterburners_decision()
    )

    assert read_value(
        base,
        "pwm1",
    ) == 255
    assert read_value(
        base,
        "pwm2",
    ) == 255
    assert read_value(
        base,
        "pwm1_enable",
    ) == 1
    assert read_value(
        base,
        "pwm2_enable",
    ) == 1


def test_safety_afterburners_can_apply_rejected_request(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    executor = FanHardwareExecutor(
        base
    )

    executor.apply(
        afterburners_decision(
            accepted=False
        )
    )

    assert read_value(
        base,
        "pwm1",
    ) == 255
    assert read_value(
        base,
        "pwm2",
    ) == 255


def test_rejected_non_safety_decision_is_refused(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    executor = FanHardwareExecutor(
        base
    )

    decision = FanControlDecision(
        accepted=False,
        requested_profile=FanProfile.QUIET,
        effective_profile=FanProfile.AUTOMATIC,
        pwm=None,
        reason="blocked",
    )

    with pytest.raises(
        ValueError
    ):
        executor.apply(
            decision
        )


def test_write_failure_rolls_back_to_automatic(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    writes = []

    def failing_writer(
        path,
        value,
    ):
        writes.append(
            (
                path.name,
                int(value),
            )
        )

        if (
            path.name
            == "pwm2_enable"
            and int(value) == 1
        ):
            raise OSError(
                "simulated sysfs failure"
            )

        path.write_text(
            str(int(value))
        )

    executor = FanHardwareExecutor(
        base,
        writer=failing_writer,
    )

    with pytest.raises(
        OSError
    ):
        executor.apply(
            manual_decision(
                pwm=225
            )
        )

    assert read_value(
        base,
        "pwm1_enable",
    ) == 2
    assert read_value(
        base,
        "pwm2_enable",
    ) == 2

    assert (
        "pwm1_enable",
        2,
    ) in writes
    assert (
        "pwm2_enable",
        2,
    ) in writes


def test_context_manager_restores_automatic(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    with FanHardwareExecutor(
        base
    ) as executor:
        executor.apply(
            manual_decision(
                pwm=225
            )
        )

        assert read_value(
            base,
            "pwm1_enable",
        ) == 1

    assert read_value(
        base,
        "pwm1_enable",
    ) == 2
    assert read_value(
        base,
        "pwm2_enable",
    ) == 2


def test_close_is_idempotent(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    executor = FanHardwareExecutor(
        base
    )

    executor.close()
    executor.close()

    assert read_value(
        base,
        "pwm1_enable",
    ) == 2
    assert read_value(
        base,
        "pwm2_enable",
    ) == 2


def test_closed_executor_rejects_new_commands(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    executor = FanHardwareExecutor(
        base
    )
    executor.close()

    with pytest.raises(
        RuntimeError
    ):
        executor.apply(
            manual_decision()
        )


def test_unverified_channel_is_rejected(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    with pytest.raises(
        ValueError
    ):
        FanHardwareExecutor(
            base,
            controlled_channels=(
                1,
                2,
                3,
            ),
        )


def test_missing_attribute_is_rejected(
    tmp_path,
):
    base = create_fake_sysfs(
        tmp_path
        / "hwmon"
    )

    (
        base
        / "pwm2_enable"
    ).unlink()

    with pytest.raises(
        RuntimeError
    ):
        FanHardwareExecutor(
            base
        )
