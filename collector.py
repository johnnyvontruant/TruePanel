#!/usr/bin/env python3
import json
import os
import subprocess
import time

from pathlib import Path

from truepanel.hardware.drive_temperatures import (
    DriveTemperatureProvider,
)


class TruePanelCollector:
    def __init__(self):
        self.state = {
            "cpu_percent": 0,
            "ram_percent": 0,
            "network": {},
            "pools": [],
            "temps": [],
            "arc": {},
            "zfs_activity": {},
            "last_updated": None,
            "smart": [],
        }
        self._last_cpu = None
        self._last_net = None

    def shell(self, cmd):
        try:
            return subprocess.check_output(
                cmd, shell=True, universal_newlines=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            return ""

    def update(self):
        self.state["cpu_percent"] = self.get_cpu_percent()
        self.state["ram_percent"] = self.get_ram_percent()
        rates = self.get_network_rates()
        self.state["network"] = self.get_network_telemetry(
            rates
        )
        self.state["pools"] = self.get_pools()
        self.state["temps"] = self.get_drive_temps()
        self.state["arc"] = self.get_arc_stats()
        self.state["zfs_activity"] = self.get_zfs_activity()
        self.state["last_updated"] = time.time()
        self.state["smart"] = self.get_smart_health()
        return self.state

    def get_cpu_percent(self):
        with open("/proc/stat") as f:
            vals = list(map(int, f.readline().split()[1:]))

        idle = vals[3] + vals[4]
        total = sum(vals)

        if self._last_cpu is None:
            self._last_cpu = (idle, total)
            return 0

        last_idle, last_total = self._last_cpu
        self._last_cpu = (idle, total)

        total_delta = total - last_total
        idle_delta = idle - last_idle

        if total_delta <= 0:
            return 0

        return round((1 - idle_delta / total_delta) * 100)

    def get_ram_percent(self):
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, value = line.split(":")
                mem[key] = int(value.split()[0])

        total = mem.get("MemTotal", 1)
        available = mem.get("MemAvailable", 0)
        return round((total - available) / total * 100)

    def get_network_rates(self):
        """Return passive per-interface transfer rates from sysfs counters."""
        now = time.monotonic()
        current = {}

        try:
            entries = list(
                Path("/sys/class/net").iterdir()
            )
        except OSError:
            self._last_net = (now, {})
            return {}

        for entry in entries:
            if entry.name == "lo":
                continue

            statistics = entry / "statistics"

            try:
                rx = int(
                    (statistics / "rx_bytes")
                    .read_text(encoding="utf-8")
                    .strip()
                )
                tx = int(
                    (statistics / "tx_bytes")
                    .read_text(encoding="utf-8")
                    .strip()
                )
            except (
                OSError,
                TypeError,
                ValueError,
            ):
                continue

            if rx < 0 or tx < 0:
                continue

            current[entry.name] = (
                rx,
                tx,
            )

        if self._last_net is None:
            self._last_net = (
                now,
                current,
            )
            return {}

        last_time, last = self._last_net
        self._last_net = (
            now,
            current,
        )

        elapsed = now - last_time

        if elapsed <= 0:
            return {}

        rates = {}

        for iface, (rx, tx) in current.items():
            previous = last.get(iface)

            if previous is None:
                continue

            old_rx, old_tx = previous
            rx_delta = rx - old_rx
            tx_delta = tx - old_tx

            # A decrease means the kernel counter was reset/wrapped or the
            # interface was recreated. Treat that sample as a new baseline
            # instead of publishing a negative or implausibly large rate.
            if rx_delta < 0 or tx_delta < 0:
                continue

            download_bytes_per_second = (
                rx_delta / elapsed
            )
            upload_bytes_per_second = (
                tx_delta / elapsed
            )

            rates[iface] = {
                # Compatibility fields used by the existing dashboard.
                "download_mb": round(
                    download_bytes_per_second
                    / 1024
                    / 1024,
                    1,
                ),
                "upload_mb": round(
                    upload_bytes_per_second
                    / 1024
                    / 1024,
                    1,
                ),
                # Explicit wire-rate fields for new API consumers.
                "download_mbps": round(
                    download_bytes_per_second
                    * 8
                    / 1_000_000,
                    2,
                ),
                "upload_mbps": round(
                    upload_bytes_per_second
                    * 8
                    / 1_000_000,
                    2,
                ),
            }

        return rates

    def get_network_telemetry(self, rates=None):
        rates = rates or {}

        try:
            result = subprocess.run(
                [
                    "ip",
                    "-json",
                    "address",
                    "show",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            address_data = json.loads(
                result.stdout
            )
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
        ):
            address_data = []

        try:
            result = subprocess.run(
                [
                    "ip",
                    "-json",
                    "route",
                    "show",
                    "default",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            route_data = json.loads(
                result.stdout
            )
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
        ):
            route_data = []

        default_interface = None

        for route in route_data:
            device = route.get("dev")

            if device:
                default_interface = str(device)
                break

        physical_interfaces = []

        try:
            physical_interfaces = sorted(
                entry.name
                for entry in Path(
                    "/sys/class/net"
                ).iterdir()
                if (
                    entry.name != "lo"
                    and (
                        entry / "device"
                    ).exists()
                )
            )
        except OSError:
            physical_interfaces = []

        physical_positions = {
            name: position
            for position, name in enumerate(
                physical_interfaces,
                start=1,
            )
        }

        telemetry = {}

        for item in address_data:
            name = str(
                item.get(
                    "ifname",
                    "",
                )
            )

            if not name or name == "lo":
                continue

            is_tailscale = (
                name.startswith(
                    "tailscale"
                )
            )

            if (
                name
                not in physical_interfaces
                and not is_tailscale
            ):
                continue

            ipv4 = None

            for address in item.get(
                "addr_info",
                [],
            ):
                if (
                    address.get("family")
                    != "inet"
                ):
                    continue

                value = address.get(
                    "local"
                )

                if value:
                    ipv4 = str(value)
                    break

            operstate = str(
                item.get(
                    "operstate",
                    "",
                )
            ).upper()

            flags = set(
                item.get(
                    "flags",
                    [],
                )
            )

            link_up = (
                operstate == "UP"
                or "LOWER_UP" in flags
            )

            rate = rates.get(
                name,
                {},
            )

            position = (
                physical_positions.get(
                    name
                )
            )

            telemetry[name] = {
                "position": position,
                "label": (
                    "Tailscale"
                    if is_tailscale
                    else (
                        f"Ethernet Port {position}"
                        if position is not None
                        else name
                    )
                ),
                "address": ipv4,
                "download_mb": (
                    rate.get(
                        "download_mb",
                        0.0,
                    )
                    if link_up
                    else 0.0
                ),
                "upload_mb": (
                    rate.get(
                        "upload_mb",
                        0.0,
                    )
                    if link_up
                    else 0.0
                ),
                "download_mbps": (
                    rate.get(
                        "download_mbps",
                        0.0,
                    )
                    if link_up
                    else 0.0
                ),
                "upload_mbps": (
                    rate.get(
                        "upload_mbps",
                        0.0,
                    )
                    if link_up
                    else 0.0
                ),
                "link_up": link_up,
                "operstate": (
                    operstate
                    or "UNKNOWN"
                ),
                "primary": (
                    name
                    == default_interface
                ),
                "kind": (
                    "tailscale"
                    if is_tailscale
                    else "lan"
                ),
            }

        return telemetry

    def get_pools(self):
        out = self.shell("zpool list -H -o name,size,alloc,free,capacity,health")
        pools = []

        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 6:
                pools.append({
                    "name": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "free": parts[3],
                    "capacity": parts[4],
                    "health": parts[5],
                })

        return pools

    def get_drive_temps(self):
        return DriveTemperatureProvider(
            runner=self.shell,
        ).records()

    def get_arc_stats(self):
        path = "/proc/spl/kstat/zfs/arcstats"

        if not os.path.exists(path):
            return {"available": False, "size_gb": 0, "hit_percent": 0}

        vals = {}

        with open(path) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 3 and parts[2].isdigit():
                    vals[parts[0]] = int(parts[2])

        size = vals.get("size", 0)
        hits = vals.get("hits", 0)
        misses = vals.get("misses", 0)
        total = hits + misses

        return {
            "available": True,
            "size_gb": round(size / 1024 / 1024 / 1024, 1),
            "hit_percent": round((hits / total) * 100, 1) if total else 0,
            "hits": hits,
            "misses": misses,
        }

    def get_zfs_activity(self):
        out = self.shell("zpool status")
        activity = {
            "scrub_running": False,
            "resilver_running": False,
            "percent": None,
            "remaining": None,
            "status_line": "",
            "problem": False,
            "problem_line": "",
        }

        if not out:
            return activity

        lower = out.lower()
        activity["scrub_running"] = "scrub in progress" in lower
        activity["resilver_running"] = "resilver in progress" in lower

        for line in out.splitlines():
            stripped = line.strip()
            lowered = stripped.lower()

            if "scan:" in lowered:
                activity["status_line"] = stripped[:80]

            if "scrub in progress" in lowered or "resilver in progress" in lowered:
                activity["status_line"] = stripped[:80]

            if "%" in stripped:
                for part in stripped.replace(",", " ").split():
                    if part.endswith("%"):
                        try:
                            activity["percent"] = int(float(part.strip("%")))
                            break
                        except Exception:
                            pass

            if "to go" in lowered:
                activity["remaining"] = stripped[:80]

            if any(word in lowered for word in ["degraded", "faulted", "unavail", "offline"]):
                activity["problem"] = True
                if not activity["problem_line"]:
                    activity["problem_line"] = stripped[:80]

            if lowered.startswith("errors:") and "no known data errors" not in lowered:
                activity["problem"] = True
                if not activity["problem_line"]:
                    activity["problem_line"] = stripped[:80]

        return activity


    def get_smart_health(self):
        disks = self.shell(
            "lsblk -ndo NAME,TYPE | awk '$2==\"disk\"{print \"/dev/\"$1}'"
        ).splitlines()

        results = []

        for disk in disks:
            if disk.endswith("/sdf"):
                continue

            health_out = self.shell(f"smartctl -H {disk} 2>/dev/null")
            attrs_out = self.shell(f"smartctl -A {disk} 2>/dev/null")

            health = "UNKNOWN"
            if "PASSED" in health_out:
                health = "PASSED"
            elif "FAILED" in health_out:
                health = "FAILED"

            record = {
                "drive": disk.split("/")[-1],
                "health": health,
                "reallocated": 0,
                "pending": 0,
                "offline_uncorrectable": 0,
                "reported_uncorrect": 0,
                "media_errors": 0,
                "critical_warning": "0x00",
            }

            for line in attrs_out.splitlines():
                lower = line.lower()
                parts = line.split()

                if parts and "reallocated_sector_ct" in lower and parts[-1].isdigit():
                    record["reallocated"] = int(parts[-1])

                if parts and "current_pending_sector" in lower and parts[-1].isdigit():
                    record["pending"] = int(parts[-1])

                if parts and "offline_uncorrectable" in lower and parts[-1].isdigit():
                    record["offline_uncorrectable"] = int(parts[-1])

                if parts and "reported_uncorrect" in lower and parts[-1].isdigit():
                    record["reported_uncorrect"] = int(parts[-1])

                if "media and data integrity errors" in lower:
                    value = line.split(":")[-1].strip()
                    if value.isdigit():
                        record["media_errors"] = int(value)

                if "critical warning" in lower:
                    record["critical_warning"] = line.split(":")[-1].strip()

            results.append(record)

        return results


if __name__ == "__main__":
    c = TruePanelCollector()

    while True:
        state = c.update()

        print("\nTruePanel Collector")
        print("-------------------")
        print(f"CPU: {state['cpu_percent']}%")
        print(f"RAM: {state['ram_percent']}%")
        print(f"Pools: {state['pools']}")
        print(f"Temps: {state['temps']}")
        print(f"Network: {state['network']}")
        print(f"ARC: {state['arc']}")
        print(f"ZFS Activity: {state['zfs_activity']}")
        print(f"Updated: {state['last_updated']}")
        print(f"SMART: {state['smart']}")

        time.sleep(2)
