from pathlib import Path

import pytest

from truepanel.compatibility.identity_verification import (
    ChassisIdentityStore,
    candidate_model,
    read_dmi_identity,
)


def make_root(
    tmp_path: Path,
    *,
    vendor="INSYDE",
    product="QW56",
    board_vendor="INSYDE",
    board="QW56",
):
    dmi = tmp_path / "sys/class/dmi/id"
    dmi.mkdir(parents=True)
    (dmi / "sys_vendor").write_text(vendor)
    (dmi / "product_name").write_text(product)
    (dmi / "product_version").write_text("")
    (dmi / "board_vendor").write_text(board_vendor)
    (dmi / "board_name").write_text(board)
    return tmp_path


def test_known_battlestation_dmi_profile_is_confirmable(tmp_path):
    root = make_root(tmp_path)
    values = read_dmi_identity(root)

    assert candidate_model(values) == "TVS-671"


def test_operator_confirmation_persists_and_matches_current_hardware(
    tmp_path,
):
    root = make_root(tmp_path)
    path = tmp_path / "verification.json"

    store = ChassisIdentityStore(
        path=path,
        clock=lambda: 123.0,
    )

    receipt = store.confirm(
        model="TVS-671",
        root=root,
    )

    assert receipt["state"] == "verified"
    assert receipt["model"] == "TVS-671"
    assert receipt["hardware_control_granted"] is False
    assert store.current(root=root) == receipt

    review = store.review(root=root)
    assert review["verified"] is True
    assert review["verified_model"] == "TVS-671"
    assert review["confirmable"] is False


def test_hardware_identity_change_invalidates_old_confirmation(
    tmp_path,
):
    root = make_root(tmp_path)
    path = tmp_path / "verification.json"
    store = ChassisIdentityStore(path=path)

    store.confirm(
        model="TVS-671",
        root=root,
    )

    dmi = root / "sys/class/dmi/id"
    (dmi / "board_name").write_text("CHANGED")

    assert store.current(root=root) is None

    review = store.review(root=root)
    assert review["verified"] is False
    assert review["previous_verification_invalidated"] is True


def test_unknown_dmi_profile_cannot_be_operator_confirmed(
    tmp_path,
):
    root = make_root(
        tmp_path,
        vendor="Dell Inc.",
        product="PowerEdge",
        board_vendor="Dell Inc.",
        board="0ABC",
    )
    store = ChassisIdentityStore(
        path=tmp_path / "verification.json"
    )

    with pytest.raises(
        ValueError,
        match="not a known operator-confirmable",
    ):
        store.confirm(
            model="TVS-671",
            root=root,
        )
