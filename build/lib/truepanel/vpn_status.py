"""Read-only VPN status telemetry for Mission Control."""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable

CommandRunner = Callable[
    [list[str]],
    subprocess.CompletedProcess[str],
]


class VpnStatusProvider:
    """Observe the qBittorrent -> Gluetun VPN chain without mutating it."""

    def __init__(
        self,
        *,
        gluetun_container: str = "ix-qbittorrent-gluetun-1",
        client_container: str = "ix-qbittorrent-qbittorrent-1",
        label: str = "ExpressVPN",
        runner: CommandRunner | None = None,
        clock: Callable[[], float] = time.monotonic,
        cache_ttl_seconds: float = 15.0,
    ) -> None:
        self.gluetun_container = gluetun_container
        self.client_container = client_container
        self.label = label
        self.runner = runner or self._run_command
        self.clock = clock
        self.cache_ttl_seconds = max(
            0.0,
            float(cache_ttl_seconds),
        )
        self._cached: dict | None = None
        self._cached_at: float | None = None

    @staticmethod
    def _run_command(
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )

    def _command(
        self,
        command: list[str],
    ) -> tuple[
        subprocess.CompletedProcess[str] | None,
        str | None,
    ]:
        try:
            return self.runner(command), None
        except (
            OSError,
            subprocess.SubprocessError,
        ) as exc:
            return None, str(exc)

    def _payload(
        self,
        state: str,
        reason: str,
        *,
        gluetun_running: bool = False,
        gluetun_healthy: bool = False,
        tunnel_up: bool = False,
        qbittorrent_bound: bool = False,
    ) -> dict:
        tone = {
            "CONNECTED": "good",
            "DEGRADED": "warn",
            "DISCONNECTED": "bad",
            "UNAVAILABLE": "neutral",
        }.get(
            state,
            "neutral",
        )

        return {
            "read_only": True,
            "label": self.label,
            "state": state,
            "tone": tone,
            "connected": state == "CONNECTED",
            "reason": reason,
            "gluetun_container": self.gluetun_container,
            "client_container": self.client_container,
            "gluetun_running": gluetun_running,
            "gluetun_healthy": gluetun_healthy,
            "tunnel_up": tunnel_up,
            "qbittorrent_bound": qbittorrent_bound,
        }

    @staticmethod
    def _tunnel_is_up(
        output: str,
    ) -> bool:
        first_line = (
            output.splitlines()[0]
            if output.splitlines()
            else ""
        )

        match = re.search(
            r"<([^>]*)>",
            first_line,
        )

        if match is None:
            return False

        flags = {
            item.strip()
            for item in match.group(1).split(",")
        }

        return {
            "UP",
            "LOWER_UP",
        }.issubset(flags)

    def _probe(self) -> dict:
        inspect_format = (
            "{{.Id}}\t"
            "{{.State.Status}}\t"
            "{{if .State.Health}}"
            "{{.State.Health.Status}}"
            "{{else}}none{{end}}"
        )

        gluetun, error = self._command(
            [
                "docker",
                "inspect",
                "--format",
                inspect_format,
                self.gluetun_container,
            ]
        )

        if error is not None:
            return self._payload(
                "UNAVAILABLE",
                "Docker status could not be queried.",
            )

        if gluetun is None:
            return self._payload(
                "UNAVAILABLE",
                "Docker status could not be queried.",
            )

        if gluetun.returncode != 0:
            stderr = (
                gluetun.stderr
                or ""
            ).lower()

            if (
                "no such object" in stderr
                or "no such container" in stderr
            ):
                return self._payload(
                    "DISCONNECTED",
                    "Gluetun container is not present.",
                )

            return self._payload(
                "UNAVAILABLE",
                "Docker status could not be queried.",
            )

        parts = (
            gluetun.stdout
            .strip()
            .split("\t")
        )

        if len(parts) != 3:
            return self._payload(
                "UNAVAILABLE",
                "Gluetun status was malformed.",
            )

        container_id, runtime_state, health = parts

        gluetun_running = (
            runtime_state == "running"
        )
        gluetun_healthy = (
            health == "healthy"
        )

        if not gluetun_running:
            return self._payload(
                "DISCONNECTED",
                "Gluetun is not running.",
                gluetun_running=False,
                gluetun_healthy=False,
            )

        tunnel, error = self._command(
            [
                "docker",
                "exec",
                self.gluetun_container,
                "ip",
                "link",
                "show",
                "tun0",
            ]
        )

        if error is not None or tunnel is None:
            return self._payload(
                "UNAVAILABLE",
                "VPN tunnel status could not be queried.",
                gluetun_running=True,
                gluetun_healthy=gluetun_healthy,
            )

        tunnel_up = (
            tunnel.returncode == 0
            and self._tunnel_is_up(
                tunnel.stdout
            )
        )

        if not tunnel_up:
            return self._payload(
                "DISCONNECTED",
                "Gluetun is running but tun0 is down.",
                gluetun_running=True,
                gluetun_healthy=gluetun_healthy,
                tunnel_up=False,
            )

        client, error = self._command(
            [
                "docker",
                "inspect",
                "--format",
                "{{.HostConfig.NetworkMode}}",
                self.client_container,
            ]
        )

        if error is not None or client is None:
            return self._payload(
                "DEGRADED",
                "VPN is up but qBittorrent binding could not be verified.",
                gluetun_running=True,
                gluetun_healthy=gluetun_healthy,
                tunnel_up=True,
            )

        if client.returncode != 0:
            return self._payload(
                "DEGRADED",
                "VPN is up but qBittorrent binding could not be verified.",
                gluetun_running=True,
                gluetun_healthy=gluetun_healthy,
                tunnel_up=True,
            )

        qbittorrent_bound = (
            client.stdout.strip()
            == f"container:{container_id}"
        )

        if not qbittorrent_bound:
            return self._payload(
                "DEGRADED",
                "qBittorrent is not bound to the Gluetun network namespace.",
                gluetun_running=True,
                gluetun_healthy=gluetun_healthy,
                tunnel_up=True,
                qbittorrent_bound=False,
            )

        if not gluetun_healthy:
            return self._payload(
                "DEGRADED",
                "VPN tunnel is up but Gluetun health is not green.",
                gluetun_running=True,
                gluetun_healthy=False,
                tunnel_up=True,
                qbittorrent_bound=True,
            )

        return self._payload(
            "CONNECTED",
            "VPN tunnel and qBittorrent binding verified.",
            gluetun_running=True,
            gluetun_healthy=True,
            tunnel_up=True,
            qbittorrent_bound=True,
        )

    def snapshot(self) -> dict:
        now = self.clock()

        if (
            self._cached is not None
            and self._cached_at is not None
            and now - self._cached_at
            < self.cache_ttl_seconds
        ):
            return dict(
                self._cached
            )

        payload = self._probe()

        self._cached = dict(
            payload
        )
        self._cached_at = now

        return payload
