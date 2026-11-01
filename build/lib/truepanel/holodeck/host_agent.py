"""Hardware-isolated Host Agent runtime for HoloDeck simulations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from truepanel.hardware.fan_control import FanControlInterlock
from truepanel.hardware.fan_runtime import FanControlRuntime
from truepanel.hardware.fan_service import FanControlService
from truepanel.hardware.thermal_fan_policy import ThermalFanPolicy
from truepanel.host.factory import build_host_agent_runtime
from truepanel.host.hooks import HostAgentSafetyServices

from .provider import HoloDeckHostProvider


class HoloDeckFanTelemetryProvider:
    """Adapt one digital-twin snapshot to Host fan-safety telemetry."""

    def __init__(self, provider: HoloDeckHostProvider):
        self.provider = provider

    def snapshot(self) -> dict[str, Any]:
        state = self.provider.snapshot()
        temperatures = list(state.get("sensors", {}).values())
        temperatures.extend(
            item.get("temp")
            for item in state.get("temps", ())
        )

        normalized = []
        for value in temperatures:
            try:
                normalized.append(float(value))
            except (TypeError, ValueError):
                continue

        return {
            "fan_status": dict(state.get("fans", {})),
            "temperatures_c": tuple(normalized),
            "telemetry_fresh": bool(
                state.get("telemetry_fresh", False)
            ),
        }

    __call__ = snapshot


class HoloDeckFanExecutor:
    """Record validated fan decisions without exposing an I/O surface."""

    def __init__(self, provider: HoloDeckHostProvider):
        self.provider = provider
        self.decisions: list[Any] = []
        self.closed = False

    def apply(self, decision: Any) -> None:
        if self.closed:
            raise RuntimeError("HoloDeck fan executor is closed")
        self.decisions.append(decision)
        self.provider.apply_fan_decision(decision)

    def close(self) -> None:
        self.closed = True


class HoloDeckOwnershipGuard:
    """Process-local ownership lease for a simulated host."""

    def __init__(self):
        self.acquired = False

    def acquire(self) -> None:
        if self.acquired:
            raise RuntimeError("HoloDeck Host Agent ownership is held")
        self.acquired = True

    def release(self) -> None:
        self.acquired = False


class HoloDeckStatusBridge:
    """Keep authoritative Host status in memory."""

    def __init__(self, fan_runtime: FanControlRuntime):
        self.fan_runtime = fan_runtime
        self.payload: dict[str, Any] | None = None

    def publish(self, reason: str | None = None) -> dict[str, Any]:
        payload = self.fan_runtime.status_payload()
        if reason is not None:
            payload["last_reason"] = reason
        self.payload = payload
        return dict(payload)

    def read(self, *, max_age: float = 30.0) -> dict[str, Any] | None:
        del max_age
        return None if self.payload is None else dict(self.payload)


class HoloDeckFanReconciliation:
    """Run real safety and thermal policy against simulated telemetry."""

    def __init__(
        self,
        safety: Any,
        policy: ThermalFanPolicy,
    ):
        self.safety = safety
        self.policy = policy

    def observe(self, telemetry: Mapping[str, Any] | None = None) -> Any:
        telemetry = telemetry or self.safety.telemetry()
        return self.policy.evaluate(
            telemetry.get("temperatures_c", ()),
            telemetry_fresh=bool(
                telemetry.get("telemetry_fresh", False)
            ),
        )

    def reconcile(self) -> Any | None:
        telemetry = self.safety.telemetry()
        decision, _telemetry = self.safety.reconcile(
            telemetry=telemetry,
        )
        return decision


def build_holodeck_host_agent_runtime(
    provider: HoloDeckHostProvider,
) -> Any:
    """Build a real HostAgentRuntime with no socket or hardware access."""

    if not isinstance(provider, HoloDeckHostProvider) or not provider.simulation:
        raise ValueError(
            "HoloDeck Host Agent requires a HoloDeck simulation provider"
        )

    telemetry = HoloDeckFanTelemetryProvider(provider)
    executor = HoloDeckFanExecutor(provider)
    service = FanControlService(
        FanControlInterlock(),
        executor,
        clock=provider.clock,
    )
    fan_runtime = FanControlRuntime(
        enabled=True,
        service=service,
    )
    status = HoloDeckStatusBridge(fan_runtime)
    ownership = HoloDeckOwnershipGuard()
    policy = ThermalFanPolicy(
        minimum_dwell_seconds=0,
        clock=provider.clock,
    )

    runtime = build_host_agent_runtime(
        fan_runtime=fan_runtime,
        safety_services=HostAgentSafetyServices(
            fan_telemetry_provider=telemetry.snapshot,
            fan_status_publisher=status.publish,
            fan_status_reader=status.read,
            fan_reconciliation_factory=lambda safety: (
                HoloDeckFanReconciliation(safety, policy)
            ),
        ),
        ownership_guard=ownership,
        fan_server_factory=lambda: None,
    )

    # Deliberately explicit inspection handles for tests and simulators.
    runtime.holodeck_executor = executor
    runtime.holodeck_ownership = ownership
    runtime.holodeck_status = status
    return runtime


__all__ = [
    "HoloDeckFanExecutor",
    "HoloDeckFanTelemetryProvider",
    "HoloDeckOwnershipGuard",
    "HoloDeckStatusBridge",
    "build_holodeck_host_agent_runtime",
]
