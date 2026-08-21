from truepanel.lifeline import (
    QNAP_TVS_X71,
    profile_keys,
    service_profile_for_config,
)


def config(*, profile=None, model=None):
    return {
        "hardware": {
            "lifeline": {
                "service_profile": profile,
                "chassis_model": model,
            }
        }
    }


def test_tvs_x71_profile_covers_battlestation_model():
    selected = QNAP_TVS_X71.for_model("TVS-671")

    assert selected is not None
    assert selected.selected_model == "TVS-671"
    assert selected.drive_service_supported is True
    assert selected.source_title == "QNAP TVS-x71 Series Hardware User Manual"


def test_profile_requires_explicit_profile_and_model():
    assert service_profile_for_config({}) is None
    assert service_profile_for_config(config(profile="qnap-tvs-x71")) is None
    assert service_profile_for_config(config(model="TVS-671")) is None


def test_profile_rejects_model_not_covered_by_source():
    assert (
        service_profile_for_config(
            config(profile="qnap-tvs-x71", model="TVS-872XT")
        )
        is None
    )


def test_profile_accepts_exact_covered_model_case_insensitively():
    selected = service_profile_for_config(
        config(profile="QNAP-TVS-X71", model="tvs-671")
    )

    assert selected is not None
    assert selected.selected_model == "TVS-671"


def test_registry_starts_narrow_instead_of_guessing_hardware_families():
    assert profile_keys() == ("qnap-tvs-x71",)
