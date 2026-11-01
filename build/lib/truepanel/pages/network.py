import json
import subprocess
from truepanel.menu.page import Page


def shell(cmd):
    return subprocess.check_output(cmd, shell=True, universal_newlines=True).strip()


class NetworkPage(Page):
    title = "Network"

    def __init__(self):
        self.index = 0

    def _get_kind(self, iface):
        return iface.get("linkinfo", {}).get("info_kind", "")

    def _get_ipv4(self, iface):
        for addr in iface.get("addr_info", []):
            if addr.get("family") == "inet":
                return addr.get("local", "0.0.0.0")
        return "0.0.0.0"

    def _interfaces(self):
        try:
            ip_json = json.loads(shell("ip -details -json address show"))
        except Exception:
            return []

        interfaces = []
        for iface in ip_json:
            if iface.get("link_type") == "loopback":
                continue

            if self._get_kind(iface) not in ["", "tun"]:
                continue

            interfaces.append((iface.get("ifname", "net"), self._get_ipv4(iface)))

        return interfaces

    def render(self, state=None):
        interfaces = self._interfaces()

        if not interfaces:
            return ["Network", "No IP Data"]

        iface, ip = interfaces[self.index % len(interfaces)]
        self.index += 1

        return [iface[:16], ip[:16]]
