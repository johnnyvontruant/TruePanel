import subprocess

from truepanel.vpn_status import (
    VpnStatusProvider,
)


def result(
    command,
    *,
    returncode=0,
    stdout="",
    stderr="",
):
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout,
        stderr,
    )


def healthy_runner(command):
    if (
        command[:3]
        == [
            "docker",
            "inspect",
            "--format",
        ]
        and command[-1]
        == "ix-qbittorrent-gluetun-1"
    ):
        return result(
            command,
            stdout=(
                "abc123\t"
                "running\t"
                "healthy\n"
            ),
        )

    if command[:3] == [
        "docker",
        "exec",
        "ix-qbittorrent-gluetun-1",
    ]:
        return result(
            command,
            stdout=(
                "3: tun0: "
                "<POINTOPOINT,MULTICAST,"
                "NOARP,UP,LOWER_UP> "
                "mtu 1171\n"
            ),
        )

    if command[-1] == (
        "ix-qbittorrent-qbittorrent-1"
    ):
        return result(
            command,
            stdout="container:abc123\n",
        )

    raise AssertionError(
        command
    )


def test_vpn_status_reports_connected():
    provider = VpnStatusProvider(
        runner=healthy_runner,
    )

    payload = provider.snapshot()

    assert payload["read_only"] is True
    assert payload["state"] == "CONNECTED"
    assert payload["tone"] == "good"
    assert payload["connected"] is True
    assert payload["gluetun_running"] is True
    assert payload["gluetun_healthy"] is True
    assert payload["tunnel_up"] is True
    assert (
        payload["qbittorrent_bound"]
        is True
    )


def test_vpn_status_reports_tunnel_down():
    def runner(command):
        response = healthy_runner(
            command
        )

        if command[:3] == [
            "docker",
            "exec",
            "ix-qbittorrent-gluetun-1",
        ]:
            return result(
                command,
                returncode=1,
                stderr=(
                    "Device tun0 does not exist"
                ),
            )

        return response

    provider = VpnStatusProvider(
        runner=runner,
    )

    payload = provider.snapshot()

    assert (
        payload["state"]
        == "DISCONNECTED"
    )
    assert payload["tone"] == "bad"
    assert payload["tunnel_up"] is False


def test_vpn_status_detects_binding_mismatch():
    def runner(command):
        if command[-1] == (
            "ix-qbittorrent-qbittorrent-1"
        ):
            return result(
                command,
                stdout="bridge\n",
            )

        return healthy_runner(
            command
        )

    provider = VpnStatusProvider(
        runner=runner,
    )

    payload = provider.snapshot()

    assert payload["state"] == "DEGRADED"
    assert payload["tone"] == "warn"
    assert (
        payload["qbittorrent_bound"]
        is False
    )


def test_vpn_status_handles_missing_docker():
    def runner(command):
        raise FileNotFoundError(
            "docker"
        )

    provider = VpnStatusProvider(
        runner=runner,
    )

    payload = provider.snapshot()

    assert (
        payload["state"]
        == "UNAVAILABLE"
    )
    assert payload["tone"] == "neutral"


def test_vpn_status_caches_probe():
    calls = []
    now = [100.0]

    def runner(command):
        calls.append(
            command
        )
        return healthy_runner(
            command
        )

    provider = VpnStatusProvider(
        runner=runner,
        clock=lambda: now[0],
        cache_ttl_seconds=15,
    )

    first = provider.snapshot()
    second = provider.snapshot()

    assert first == second
    assert len(calls) == 3

    now[0] = 116.0
    provider.snapshot()

    assert len(calls) == 6
