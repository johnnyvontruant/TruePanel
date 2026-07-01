#!/usr/bin/env python3
import os
import time
import subprocess


class TruePanelCollector:
    def __init__(self):
        self.state = {
            "cpu_percent": 0,
            "ram_percent": 0,
            "network": {},
            "pools": [],
            "temps": [],
            "last_updated": None,
        }

        self._last_cpu = None
        self._last_net = None

    def shell(self, cmd):
        try:
            return subprocess.check_output(
                cmd,
                shell=True,
                universal_newlines=True,
                stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            return ""

    def update(self):
        self.state["cpu_percent"] = self.get_cpu_percent()
        self.state["ram_percent"] = self.get_ram_percent()
        self.state["network"] = self.get_network_rates()
        self.state["pools"] = self.get_pools()
        self.state["temps"] = self.get_drive_temps()
        self.state["last_updated"] = time.time()
        return self.state

    def get_cpu_percent(self):
        with open("/proc/stat") as f:
            parts = f.readline().split()[1:]

        vals = list(map(int, parts))
        idle = vals[3] + vals[4]
        total = sum(vals)

        if self._last_cpu is None:
            self._last_cpu = (idle, total)
            return 0

        last_idle, last_total = self._last_cpu
        self._last_cpu = (idle, total)

        idle_delta = idle - last_idle
        total_delta = total - last_total

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
        now = time.time()
        current = {}

        with open("/proc/net/dev") as f:
            for line in f.readlines()[2:]:
                iface, data = line.split(":")
                iface = iface.strip()

                if iface == "lo":
                    continue

                parts = data.split()
                rx = int(parts[0])
                tx = int(parts[8])
                current[iface] = (rx, tx)

        if self._last_net is None:
            self._last_net = (now, current)
            return {}

        last_time, last = self._last_net
        elapsed = max(now - last_time, 1)
        self._last_net = (now, current)

        rates = {}

        for iface, (rx, tx) in current.items():
            if iface not in last:
                continue

            old_rx, old_tx = last[iface]

            rates[iface] = {
                "download_mb": round((rx - old_rx) / elapsed / 1024 / 1024, 1),
                "upload_mb": round((tx - old_tx) / elapsed / 1024 / 1024, 1),
            }

        return rates

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
        disks = self.shell(
            "lsblk -ndo NAME,TYPE | awk '$2==\"disk\"{print \"/dev/\"$1}'"
        ).splitlines()

        temps = []

        for disk in disks:
            if disk.endswith("/sdf"):
                continue

            out = self.shell(f"smartctl -a {disk} 2>/dev/null")
            temp = None

            for line in out.splitlines():
                lower = line.lower()

                if "temperature_celsius" in lower or "airflow_temperature" in lower:
                    parts = line.split()
                    for part in reversed(parts):
                        cleaned = part.strip("()")
                        if cleaned.isdigit():
                            temp = int(cleaned)
                            break

                if temp is None and line.strip().startswith("Temperature:"):
                    for part in line.split():
                        if part.isdigit():
                            temp = int(part)
                            break

                if temp is not None:
                    break

            if temp is not None:
                temps.append({
                    "drive": disk.split("/")[-1],
                    "temp": temp,
                })

        temps.sort(key=lambda x: x["temp"], reverse=True)
        return temps


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
        print(f"Updated: {state['last_updated']}")

        time.sleep(2)
