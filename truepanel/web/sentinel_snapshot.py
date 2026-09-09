"""Mission Control snapshot extension for Project SENTINEL.

This module composes existing Mission Control evidence with a cached, read-only
TrueNAS topology provider. It does not change the established snapshot module,
which keeps the integration easy to disable or roll back while SENTINEL
matures.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from truepanel.health import ServiceStatusProvider
from truepanel.sentinel import (
    CachedTopologyProvider,
    build_flight_director_explanation,
    build_sentinel_snapshot,
)

from .snapshot import SnapshotService as _SnapshotService


class SentinelSnapshotService(_SnapshotService):
    """Attach bounded topology evidence and deterministic SENTINEL output."""

    def __init__(
        self,
        *args,
        sentinel_topology_provider=None,
        **kwargs,
    ) -> None:
        if kwargs.get("service_status_provider") is None:
            kwargs["service_status_provider"] = ServiceStatusProvider()

        super().__init__(*args, **kwargs)
        self.sentinel_topology_provider = (
            sentinel_topology_provider
            if sentinel_topology_provider is not None
            else CachedTopologyProvider()
        )

    @staticmethod
    def _topology_unavailable() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "read_only": True,
            "source": "truenas.middleware",
            "available": False,
            "datasets": [],
            "applications": [],
            "relationships": [],
        }

    def _sentinel_topology_payload(self) -> dict[str, Any]:
        provider = self.sentinel_topology_provider

        if provider is None:
            return self._topology_unavailable()

        try:
            payload = provider.snapshot()
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            AttributeError,
        ):
            return self._topology_unavailable()

        if not isinstance(payload, dict):
            return self._topology_unavailable()

        result = dict(payload)
        result.setdefault("available", True)
        result["read_only"] = True
        return result

    @staticmethod
    def _mark_topology_unknown(
        sentinel: dict[str, Any],
    ) -> None:
        assessment = sentinel.get("assessment")
        if not isinstance(assessment, dict):
            return

        unknowns = assessment.get("unknowns")
        if not isinstance(unknowns, list):
            return

        message = (
            "TrueNAS dataset/application topology evidence is unavailable; "
            "SENTINEL cannot prove dataset-to-application dependencies."
        )
        if message not in unknowns:
            unknowns.append(message)
            unknowns.sort()

    @staticmethod
    def _live_incident_package(
        sentinel: dict[str, Any],
        report: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert one proved live impact report into explanation input."""

        reachable = [
            deepcopy(item)
            for item in report.get("reachable", [])
            if isinstance(item, dict)
        ]
        assessment = sentinel.get("assessment")
        assessment = assessment if isinstance(assessment, dict) else {}
        unknowns = sorted(
            {
                str(item).strip()
                for item in assessment.get("unknowns", [])
                if str(item).strip()
            }
        )
        return {
            "source_device": str(report.get("source_device") or "").strip(),
            "proved_blast_radius": reachable,
            "backup_evidence": [
                deepcopy(item)
                for item in reachable
                if str(item.get("kind") or "").strip() == "backup_evidence"
            ],
            "unknowns": unknowns,
            "language_guard": (
                "Objects absent from the proved blast radius are not automatically "
                "classified as unaffected."
            ),
        }

    @classmethod
    def _attach_live_explanations(cls, sentinel: dict[str, Any]) -> None:
        """Attach deterministic Flight Director language to active reports only.

        An empty explanation list means no active impact report was available.
        It is intentionally not an all-clear or healthy-system assertion.
        """

        reports = [
            report
            for report in sentinel.get("impact_reports", [])
            if isinstance(report, dict)
        ]
        reports.sort(
            key=lambda report: (
                str(report.get("source_device") or ""),
                str(report.get("source_node_id") or ""),
            )
        )
        sentinel["explanations"] = [
            build_flight_director_explanation(
                cls._live_incident_package(sentinel, report)
            )
            for report in reports
        ]

    def status(self) -> dict[str, Any]:
        payload = super().status()
        payload = payload if isinstance(payload, dict) else {}
        result = dict(payload)
        result["sentinel_topology"] = self._sentinel_topology_payload()

        try:
            result["sentinel"] = build_sentinel_snapshot(result)
            if result["sentinel_topology"].get("available") is False:
                self._mark_topology_unknown(result["sentinel"])
            self._attach_live_explanations(result["sentinel"])
        except (TypeError, ValueError, ArithmeticError, AttributeError):
            result["sentinel"] = {
                "schema_version": 1,
                "read_only": True,
                "control_authority": False,
                "graph": {"nodes": [], "edges": []},
                "assessment": {
                    "state": "UNKNOWN",
                    "claims": [],
                    "unknowns": [
                        "SENTINEL could not build a deterministic assessment "
                        "from the current snapshot."
                    ],
                },
                "impact_reports": [],
                "explanations": [],
                "available": False,
            }

        return result


__all__ = ["SentinelSnapshotService"]
