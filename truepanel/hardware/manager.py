"""
TruePanel Hardware Abstraction Layer.

HardwareManager provides one lazy, testable entry point for TruePanel's
hardware controllers and logical hardware services.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .a125 import A125Controller
from .buzzer import Buzzer
from .enclosure import EnclosureController
from .health import StorageHealthService
from .inventory import StorageInventory
from .smart import SmartctlProvider
from .topology import TopologyResolver


Factory = Callable[[], Any]


def _load_hardware_config() -> dict:
    from truepanel.config.loader import load_config

    config = load_config()
    hardware = config.get("hardware", {})

    return hardware if isinstance(hardware, dict) else {}


def _create_buzzer() -> Buzzer:
    from truepanel.config.loader import load_config

    config = load_config()
    return Buzzer(config.get("buzzer", {}))


class HardwareManager:
    """
    Lazy registry for TruePanel hardware controllers and services.

    Controllers are created only when first accessed. Plugins and platform
    ports may register or replace factories without changing Mission Control.
    """

    def __init__(
        self,
        *,
        enclosure_factory: Factory | None = None,
        buzzer_factory: Factory | None = None,
        a125_factory: Factory | None = None,
        topology_factory: Factory | None = None,
        inventory_factory: Factory | None = None,
        smart_factory: Factory | None = None,
        health_factory: Factory | None = None,
    ) -> None:
        self._factories: dict[str, Factory] = {
            "enclosure": enclosure_factory or EnclosureController,
            "buzzer": buzzer_factory or _create_buzzer,
            "a125": a125_factory or A125Controller,
            "topology": topology_factory or self._create_topology,
            "inventory": inventory_factory or self._create_inventory,
            "smart": smart_factory or self._create_smart,
            "health": health_factory or self._create_health,
        }

        self._instances: dict[str, Any] = {}

    def _create_topology(self) -> TopologyResolver:
        hardware = _load_hardware_config()
        topology = hardware.get("topology", {})

        if not isinstance(topology, dict):
            topology = {}

        return TopologyResolver(topology)

    def _create_inventory(self) -> StorageInventory:
        hardware = _load_hardware_config()

        return StorageInventory(
            enclosure=self.enclosure,
            topology=self.topology,
            config=hardware.get("inventory", {}),
        )

    def _create_smart(self) -> SmartctlProvider:
        hardware = _load_hardware_config()
        smart = hardware.get("smart", {})

        if not isinstance(smart, dict):
            smart = {}

        return SmartctlProvider(
            executable=str(smart.get("executable", "smartctl")),
            timeout=float(smart.get("timeout", 10.0)),
        )

    def _create_health(self) -> StorageHealthService:
        hardware = _load_hardware_config()
        health = hardware.get("health", {})

        if not isinstance(health, dict):
            health = {}

        return StorageHealthService(
            inventory=self.inventory,
            provider=self.smart,
            warning_temperature_c=int(
                health.get("warning_temperature_c", 45)
            ),
            critical_temperature_c=int(
                health.get("critical_temperature_c", 55)
            ),
            nvme_warning_percentage_used=int(
                health.get("nvme_warning_percentage_used", 80)
            ),
            nvme_critical_percentage_used=int(
                health.get("nvme_critical_percentage_used", 95)
            ),
        )

    def _get(self, name: str) -> Any:
        if name not in self._instances:
            self._instances[name] = self._factories[name]()

        return self._instances[name]

    @property
    def enclosure(self) -> EnclosureController:
        return self._get("enclosure")

    @property
    def buzzer(self) -> Buzzer:
        return self._get("buzzer")

    @property
    def a125(self) -> A125Controller:
        return self._get("a125")

    @property
    def lcd(self) -> A125Controller:
        return self.a125

    @property
    def topology(self) -> TopologyResolver:
        return self._get("topology")

    @property
    def inventory(self) -> StorageInventory:
        return self._get("inventory")

    @property
    def smart(self) -> SmartctlProvider:
        return self._get("smart")

    @property
    def health(self) -> StorageHealthService:
        return self._get("health")

    def is_loaded(self, name: str) -> bool:
        return name in self._instances

    def loaded(self) -> tuple[str, ...]:
        return tuple(sorted(self._instances))

    def reset(self, name: str | None = None) -> None:
        if name is None:
            self._instances.clear()
            return

        if name not in self._factories:
            raise KeyError(f"Unknown hardware controller: {name}")

        self._instances.pop(name, None)

        if name in {"enclosure", "topology"}:
            self._instances.pop("inventory", None)
            self._instances.pop("health", None)

        if name in {"inventory", "smart"}:
            self._instances.pop("health", None)

    def register(
        self,
        name: str,
        factory: Factory,
        *,
        replace: bool = False,
    ) -> None:
        if not name:
            raise ValueError("Hardware controller name cannot be empty")

        if not callable(factory):
            raise TypeError("Hardware controller factory must be callable")

        if name in self._factories and not replace:
            raise ValueError(f"Hardware controller already registered: {name}")

        self._factories[name] = factory
        self._instances.pop(name, None)

    def controller(self, name: str) -> Any:
        if name not in self._factories:
            raise KeyError(f"Unknown hardware controller: {name}")

        return self._get(name)

    def registered(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


__all__ = ["HardwareManager"]
