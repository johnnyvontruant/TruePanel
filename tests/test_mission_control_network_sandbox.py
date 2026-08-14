from pathlib import Path


REQUIRED_ADDRESS_FAMILIES = (
    "RestrictAddressFamilies="
    "AF_INET AF_INET6 AF_UNIX AF_NETLINK"
)


def test_installer_allows_netlink_for_network_telemetry():
    source = Path("install.sh").read_text()

    assert REQUIRED_ADDRESS_FAMILIES in source


def test_start_script_allows_netlink_for_network_telemetry():
    source = Path(
        "start-truepanel.sh"
    ).read_text()

    assert REQUIRED_ADDRESS_FAMILIES in source


def test_mission_control_sandbox_does_not_regress_to_old_contract():
    forbidden = (
        "RestrictAddressFamilies="
        "AF_INET AF_INET6 AF_UNIX\n"
    )

    for path in (
        Path("install.sh"),
        Path("start-truepanel.sh"),
    ):
        assert forbidden not in path.read_text()
