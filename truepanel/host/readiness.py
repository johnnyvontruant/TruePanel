"""Passive standalone Host Agent deployment-readiness reporting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import agent

SERVICE_UNIT_PATH = Path(
    "/etc/systemd/system/truepanel-host-agent.service"
)
CUTOVER_MARKER_PATH = Path(
    "/run/truepanel/standalone-host-agent.enabled"
)


@dataclass(frozen=True)
class HostReadinessCheck:
    """One passive readiness assertion."""

    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HostReadinessReport:
    """Passive snapshot of standalone Host Agent deployment readiness."""

    root: str
    checks: tuple[HostReadinessCheck, ...]

    @property
    def prepared_safely(self) -> bool:
        return all(
            check.passed
            for check in self.checks
        )

    @property
    def activation_state(self) -> str:
        for check in self.checks:
            if check.name == "python_activation_locked":
                return (
                    "locked"
                    if check.passed
                    else "unlocked"
                )

        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "root": self.root,
            "prepared_safely": self.prepared_safely,
            "activation_state": self.activation_state,
            "service_unit_path": str(SERVICE_UNIT_PATH),
            "cutover_marker_path": str(CUTOVER_MARKER_PATH),
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
        }


def _rooted(
    root: str | Path,
    absolute_path: Path,
) -> Path:
    base = Path(root)

    if base == Path("/"):
        return absolute_path

    return base / absolute_path.relative_to("/")


def collect_host_readiness(
    *,
    root: str | Path = "/",
    activation_enabled: bool | None = None,
) -> HostReadinessReport:
    """
    Inspect standalone Host Agent deployment prerequisites without mutation.

    This report describes whether the dormant service scaffold is installed
    safely. It does not determine a live hardware owner, acquire the Host
    ownership lock, create the cutover marker, or grant activation authority.
    """

    service_path = _rooted(
        root,
        SERVICE_UNIT_PATH,
    )
    marker_path = _rooted(
        root,
        CUTOVER_MARKER_PATH,
    )

    try:
        service_text = service_path.read_text(
            encoding="utf-8"
        )
        service_error = None
    except OSError as error:
        service_text = ""
        service_error = error

    if activation_enabled is None:
        activation_enabled = bool(
            agent.STANDALONE_PRODUCTION_ACTIVATED
        )

    service_available = service_error is None
    expected_exec = (
        "ExecStart=$PYTHON_BIN -m truepanel.host.agent"
    )
    expected_condition = (
        "ConditionPathExists=/run/truepanel/"
        "standalone-host-agent.enabled"
    )

    checks = (
        HostReadinessCheck(
            "service_unit_installed",
            service_available,
            (
                "Standalone Host Agent service scaffold is installed."
                if service_available
                else (
                    "Standalone Host Agent service scaffold is unavailable: "
                    f"{service_error}"
                )
            ),
        ),
        HostReadinessCheck(
            "service_exec_target",
            (
                service_available
                and expected_exec in service_text
            ),
            (
                "Service ExecStart targets truepanel.host.agent."
                if service_available and expected_exec in service_text
                else "Service ExecStart does not match the guarded Host Agent entry point."
            ),
        ),
        HostReadinessCheck(
            "systemd_condition_gate",
            (
                service_available
                and expected_condition in service_text
            ),
            (
                "Ephemeral systemd cutover condition is present."
                if service_available and expected_condition in service_text
                else "Ephemeral systemd cutover condition is missing."
            ),
        ),
        HostReadinessCheck(
            "service_not_enableable",
            (
                service_available
                and "[Install]" not in service_text
            ),
            (
                "Service has no [Install] section and remains dormant."
                if service_available and "[Install]" not in service_text
                else "Service contains an [Install] section or is unavailable."
            ),
        ),
        HostReadinessCheck(
            "python_activation_locked",
            not activation_enabled,
            (
                "Python standalone activation gate is locked."
                if not activation_enabled
                else "Python standalone activation gate is unlocked."
            ),
        ),
        HostReadinessCheck(
            "cutover_marker_absent",
            not marker_path.exists(),
            (
                "Ephemeral cutover marker is absent."
                if not marker_path.exists()
                else "Ephemeral cutover marker is present."
            ),
        ),
    )

    return HostReadinessReport(
        root=str(Path(root)),
        checks=checks,
    )


def format_host_readiness(
    report: HostReadinessReport,
) -> str:
    """Format an operator-friendly readiness summary."""

    lines = [
        "TruePanel Standalone Host Agent Readiness",
        "=========================================",
        "",
    ]

    for check in report.checks:
        state = "PASS" if check.passed else "REVIEW"
        lines.append(
            f"[{state}] {check.name}: {check.detail}"
        )

    lines.extend(
        [
            "",
            (
                "Prepared safely: YES"
                if report.prepared_safely
                else "Prepared safely: NO"
            ),
            (
                "Standalone activation: "
                f"{report.activation_state.upper()}"
            ),
        ]
    )

    return "\n".join(lines)


__all__ = [
    "CUTOVER_MARKER_PATH",
    "HostReadinessCheck",
    "HostReadinessReport",
    "SERVICE_UNIT_PATH",
    "collect_host_readiness",
    "format_host_readiness",
]
