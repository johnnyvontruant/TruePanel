"""Read-only SENTINEL adapter for current TruePanel snapshot evidence."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .graph import KnowledgeGraph
from .models import (
    ClaimStatus,
    Confidence,
    EvidenceRef,
    KnowledgeEdge,
    KnowledgeNode,
    NodeKind,
    Relation,
    SentinelAssessment,
    SentinelClaim,
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _attributes(**values: Any) -> tuple[tuple[str, Any], ...]:
    return tuple(
        sorted(
            (key, value)
            for key, value in values.items()
            if value not in (None, "")
        )
    )


def _pool_from_path(path: Any) -> str | None:
    text = _text(path)
    if not text.startswith("/mnt/"):
        return None
    parts = PurePosixPath(text).parts
    if len(parts) < 3:
        return None
    return parts[2]


def _smart_actionable(record: dict[str, Any]) -> bool:
    if _text(record.get("health")).upper() == "FAILED":
        return True

    for key in (
        "reallocated",
        "pending",
        "offline_uncorrectable",
        "reported_uncorrect",
        "media_errors",
    ):
        try:
            if int(record.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue

    warning = _text(record.get("critical_warning")).lower()
    return warning not in {"", "0", "0x0", "0x00"}


def build_sentinel_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate existing observations into a deterministic explanation model.

    The adapter performs no I/O and grants no control authority. Missing
    evidence becomes an explicit unknown rather than a guessed relationship.
    """

    graph = KnowledgeGraph()
    assessment = SentinelAssessment()

    system = _dict(payload.get("system"))
    hostname = _text(system.get("hostname")) or "TrueNAS host"
    host_id = "hardware:host"
    graph.add_node(
        KnowledgeNode(
            id=host_id,
            kind=NodeKind.HARDWARE,
            label=hostname,
            evidence=(
                EvidenceRef(
                    source="snapshot.system",
                    reference="system.hostname",
                    summary=f"Observed host identity: {hostname}",
                ),
            ),
        )
    )

    storage = _dict(payload.get("storage"))
    pool_ids: dict[str, str] = {}
    for pool in _list(storage.get("pools")):
        if not isinstance(pool, dict):
            continue
        name = _text(pool.get("name") or pool.get("pool"))
        if not name:
            continue
        pool_id = f"pool:{name}"
        pool_ids[name] = pool_id
        state = _text(pool.get("health") or pool.get("state")) or None
        evidence = EvidenceRef(
            source="snapshot.storage",
            reference=f"storage.pools[{name}]",
            summary=f"Pool {name} observed with state {state or 'unknown'}",
        )
        graph.add_node(
            KnowledgeNode(
                id=pool_id,
                kind=NodeKind.POOL,
                label=name,
                state=state,
                evidence=(evidence,),
            )
        )
        graph.add_edge(
            KnowledgeEdge(
                source=host_id,
                target=pool_id,
                relation=Relation.HOSTS,
                evidence=(evidence,),
            )
        )

    vdev_ids: dict[tuple[str, str], str] = {}
    for record in _list(storage.get("devices")):
        if not isinstance(record, dict):
            continue
        device = _text(record.get("device"))
        member = _text(record.get("member_id"))
        identity = device or member
        if not identity:
            continue

        disk_id = f"disk:{identity}"
        disk_evidence = EvidenceRef(
            source="snapshot.storage.devices",
            reference=identity,
            summary=f"Observed storage member {identity}",
        )
        graph.add_node(
            KnowledgeNode(
                id=disk_id,
                kind=NodeKind.DISK,
                label=device or member,
                state=_text(record.get("zfs_state")) or None,
                attributes=_attributes(
                    member_id=member,
                    physical_bay=record.get("physical_bay"),
                    model=record.get("model"),
                    serial_last4=record.get("serial_last4"),
                    capacity_bytes=record.get("capacity_bytes"),
                ),
                evidence=(disk_evidence,),
            )
        )

        bay = record.get("physical_bay")
        if bay not in (None, ""):
            bay_id = f"bay:{bay}"
            graph.add_node(
                KnowledgeNode(
                    id=bay_id,
                    kind=NodeKind.BAY,
                    label=f"Bay {bay}",
                    evidence=(disk_evidence,),
                )
            )
            graph.add_edge(
                KnowledgeEdge(
                    source=bay_id,
                    target=disk_id,
                    relation=Relation.CONTAINS,
                    evidence=(disk_evidence,),
                )
            )

        pool = _text(record.get("pool"))
        vdev = _text(record.get("vdev"))
        target_id = pool_ids.get(pool)
        if pool and vdev and target_id:
            key = (pool, vdev)
            vdev_id = vdev_ids.setdefault(key, f"vdev:{pool}:{vdev}")
            if graph.node(vdev_id) is None:
                graph.add_node(
                    KnowledgeNode(
                        id=vdev_id,
                        kind=NodeKind.VDEV,
                        label=vdev,
                        evidence=(disk_evidence,),
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        source=vdev_id,
                        target=target_id,
                        relation=Relation.MEMBER_OF,
                        evidence=(disk_evidence,),
                    )
                )
            graph.add_edge(
                KnowledgeEdge(
                    source=disk_id,
                    target=vdev_id,
                    relation=Relation.MEMBER_OF,
                    evidence=(disk_evidence,),
                )
            )
        elif target_id:
            graph.add_edge(
                KnowledgeEdge(
                    source=disk_id,
                    target=target_id,
                    relation=Relation.MEMBER_OF,
                    evidence=(disk_evidence,),
                )
            )

    for record in _list(storage.get("smart")):
        if not isinstance(record, dict) or not _smart_actionable(record):
            continue
        device = _text(record.get("device") or record.get("drive")) or "unknown"
        evidence = EvidenceRef(
            source="snapshot.storage.smart",
            reference=device,
            summary=f"Actionable SMART evidence observed for {device}",
        )
        assessment.claims.append(
            SentinelClaim(
                id=f"storage.smart:{device}",
                statement=f"{device} has actionable SMART evidence.",
                status=ClaimStatus.CONFIRMED,
                confidence=Confidence.HIGH,
                evidence=(evidence,),
            )
        )

    cargo = _dict(payload.get("cargo_bay"))
    if cargo:
        for source in ("sonarr", "radarr"):
            app_id = f"application:{source}"
            graph.add_node(
                KnowledgeNode(
                    id=app_id,
                    kind=NodeKind.APPLICATION,
                    label=source.title(),
                    evidence=(
                        EvidenceRef(
                            source="cargo_bay",
                            reference=source,
                            summary=f"Cargo Bay observes {source.title()}",
                        ),
                    ),
                )
            )
            graph.add_edge(
                KnowledgeEdge(
                    source=host_id,
                    target=app_id,
                    relation=Relation.HOSTS,
                )
            )

        groups = _dict(cargo.get("groups"))
        for group_name in ("tv", "movies"):
            for item in _list(groups.get(group_name)):
                if not isinstance(item, dict):
                    continue
                source = _text(item.get("source")) or "unknown"
                identity = _text(
                    item.get("history_id")
                    or item.get("current_file_id")
                    or item.get("media_id")
                )
                if not identity:
                    continue
                cargo_id = f"cargo:{source}:{identity}"
                title = _text(item.get("title")) or cargo_id
                exists = item.get("exists")
                evidence = EvidenceRef(
                    source="cargo_bay",
                    reference=f"{group_name}:{identity}",
                    summary=f"Cargo Bay resolved {title}",
                    observed_at=item.get("imported_at"),
                )
                graph.add_node(
                    KnowledgeNode(
                        id=cargo_id,
                        kind=NodeKind.CARGO,
                        label=title,
                        state=(
                            "PRESENT"
                            if exists is True
                            else "MISSING"
                            if exists is False
                            else "UNKNOWN"
                        ),
                        attributes=_attributes(
                            current_path=item.get("current_path"),
                            resolution=item.get("resolution"),
                            moved_since_import=item.get("moved_since_import"),
                        ),
                        evidence=(evidence,),
                    )
                )
                app_id = f"application:{source}"
                if graph.node(app_id) is not None:
                    graph.add_edge(
                        KnowledgeEdge(
                            source=app_id,
                            target=cargo_id,
                            relation=Relation.PRODUCES,
                            evidence=(evidence,),
                        )
                    )
                pool_name = _pool_from_path(item.get("current_path"))
                pool_id = pool_ids.get(pool_name or "")
                if pool_id:
                    graph.add_edge(
                        KnowledgeEdge(
                            source=pool_id,
                            target=cargo_id,
                            relation=Relation.SERVES,
                            evidence=(evidence,),
                        )
                    )

        summary = _dict(cargo.get("summary"))
        try:
            unresolved = int(summary.get("unresolved") or 0)
        except (TypeError, ValueError):
            unresolved = 0
        if unresolved > 0:
            evidence = EvidenceRef(
                source="cargo_bay",
                reference="summary.unresolved",
                summary=f"Cargo Bay reports {unresolved} unresolved item(s)",
            )
            assessment.claims.append(
                SentinelClaim(
                    id="cargo.unresolved",
                    statement=f"Cargo Bay has {unresolved} unresolved item(s).",
                    status=ClaimStatus.CONFIRMED,
                    confidence=Confidence.HIGH,
                    evidence=(evidence,),
                )
            )

        backup = _dict(cargo.get("backup"))
        if backup.get("tracking") is not True:
            assessment.unknowns.append(
                "Independent backup evidence is not available for Cargo Bay; "
                "SENTINEL cannot infer that cargo is protected or unprotected."
            )

    if assessment.claims:
        assessment.state = "REVIEW"

    return {
        "schema_version": 1,
        "read_only": True,
        "control_authority": False,
        "graph": graph.to_payload(),
        "assessment": assessment.to_payload(),
    }
