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


def _ensure_pool_node(
    graph: KnowledgeGraph,
    pool_ids: dict[str, str],
    *,
    name: str,
    host_id: str,
    state: str | None = None,
    evidence: EvidenceRef | None = None,
) -> str:
    pool_id = pool_ids.get(name) or f"pool:{name}"
    pool_ids[name] = pool_id

    if graph.node(pool_id) is None:
        graph.add_node(
            KnowledgeNode(
                id=pool_id,
                kind=NodeKind.POOL,
                label=name,
                state=state,
                evidence=(evidence,) if evidence is not None else (),
            )
        )
        graph.add_edge(
            KnowledgeEdge(
                source=host_id,
                target=pool_id,
                relation=Relation.HOSTS,
                evidence=(evidence,) if evidence is not None else (),
            )
        )

    return pool_id


def _add_topology(
    graph: KnowledgeGraph,
    assessment: SentinelAssessment,
    topology: dict[str, Any],
    *,
    pool_ids: dict[str, str],
    host_id: str,
) -> None:
    if not topology:
        assessment.unknowns.append(
            "TrueNAS dataset/application topology evidence is unavailable; "
            "SENTINEL cannot prove dataset-to-application dependencies."
        )
        return

    dataset_ids: dict[str, str] = {}

    for dataset in _list(topology.get("datasets")):
        if not isinstance(dataset, dict):
            continue

        dataset_name = _text(dataset.get("id"))
        pool = _text(dataset.get("pool"))
        if not dataset_name or not pool:
            continue

        evidence = EvidenceRef(
            source="sentinel_topology.datasets",
            reference=dataset_name,
            summary=(
                f"TrueNAS middleware reports dataset {dataset_name} "
                f"on pool {pool}"
            ),
        )
        pool_id = _ensure_pool_node(
            graph,
            pool_ids,
            name=pool,
            host_id=host_id,
            evidence=evidence,
        )
        dataset_id = f"dataset:{dataset_name}"
        dataset_ids[dataset_name] = dataset_id

        if graph.node(dataset_id) is None:
            graph.add_node(
                KnowledgeNode(
                    id=dataset_id,
                    kind=NodeKind.DATASET,
                    label=_text(dataset.get("name")) or dataset_name,
                    state=(
                        "LOCKED"
                        if dataset.get("locked") is True
                        else "AVAILABLE"
                        if dataset.get("locked") is False
                        else None
                    ),
                    attributes=_attributes(
                        dataset=dataset_name,
                        pool=pool,
                        type=dataset.get("type"),
                        mountpoint=dataset.get("mountpoint"),
                    ),
                    evidence=(evidence,),
                )
            )

        graph.add_edge(
            KnowledgeEdge(
                source=pool_id,
                target=dataset_id,
                relation=Relation.SERVES,
                evidence=(evidence,),
            )
        )

    application_ids: dict[str, str] = {}

    for application in _list(topology.get("applications")):
        if not isinstance(application, dict):
            continue

        app_identity = _text(application.get("id"))
        if not app_identity:
            continue

        app_id = f"application:{app_identity}"
        application_ids[app_identity] = app_id
        evidence = EvidenceRef(
            source="sentinel_topology.applications",
            reference=app_identity,
            summary=f"TrueNAS middleware reports application {app_identity}",
        )

        if graph.node(app_id) is None:
            graph.add_node(
                KnowledgeNode(
                    id=app_id,
                    kind=NodeKind.APPLICATION,
                    label=_text(application.get("name")) or app_identity,
                    state=_text(application.get("state")) or None,
                    attributes=_attributes(
                        paths=tuple(_list(application.get("paths"))),
                    ),
                    evidence=(evidence,),
                )
            )
            graph.add_edge(
                KnowledgeEdge(
                    source=host_id,
                    target=app_id,
                    relation=Relation.HOSTS,
                    evidence=(evidence,),
                )
            )

    for relationship in _list(topology.get("relationships")):
        if not isinstance(relationship, dict):
            continue

        dataset_name = _text(relationship.get("dataset_id"))
        application_name = _text(relationship.get("application_id"))
        dataset_id = dataset_ids.get(dataset_name)
        app_id = application_ids.get(application_name)

        if not dataset_id or not app_id:
            continue

        path = _text(relationship.get("path"))
        source = _text(relationship.get("source")) or "sentinel_topology"
        evidence = EvidenceRef(
            source=source,
            reference=f"{dataset_name}->{application_name}",
            summary=(
                f"Application {application_name} contains literal TrueNAS "
                f"path {path} under dataset {dataset_name}"
            ),
        )
        graph.add_edge(
            KnowledgeEdge(
                source=dataset_id,
                target=app_id,
                relation=Relation.SERVES,
                evidence=(evidence,),
            )
        )


def _add_cargo(
    graph: KnowledgeGraph,
    assessment: SentinelAssessment,
    cargo: dict[str, Any],
    *,
    pool_ids: dict[str, str],
    host_id: str,
) -> dict[str, str]:
    cargo_by_path: dict[str, str] = {}

    if not cargo:
        return cargo_by_path

    for source in ("sonarr", "radarr"):
        app_id = f"application:{source}"
        if graph.node(app_id) is None:
            evidence = EvidenceRef(
                source="cargo_bay",
                reference=source,
                summary=f"Cargo Bay observes {source.title()}",
            )
            graph.add_node(
                KnowledgeNode(
                    id=app_id,
                    kind=NodeKind.APPLICATION,
                    label=source.title(),
                    evidence=(evidence,),
                )
            )
            graph.add_edge(
                KnowledgeEdge(
                    source=host_id,
                    target=app_id,
                    relation=Relation.HOSTS,
                    evidence=(evidence,),
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
            current_path = _text(item.get("current_path"))
            evidence = EvidenceRef(
                source="cargo_bay",
                reference=f"{group_name}:{identity}",
                summary=f"Cargo Bay resolved {title}",
                observed_at=item.get("imported_at"),
            )

            if graph.node(cargo_id) is None:
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
                            current_path=current_path or None,
                            resolution=item.get("resolution"),
                            moved_since_import=item.get("moved_since_import"),
                        ),
                        evidence=(evidence,),
                    )
                )

            if current_path:
                cargo_by_path[current_path] = cargo_id

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

            pool_name = _pool_from_path(current_path)
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
        return cargo_by_path

    backup_state = _text(backup.get("state")) or "UNKNOWN"
    if backup_state in {"REVIEW", "INVALID"}:
        evidence = EvidenceRef(
            source="cargo_bay.backup",
            reference="backup.state",
            summary=f"Cargo Bay backup evidence state is {backup_state}",
        )
        assessment.claims.append(
            SentinelClaim(
                id="cargo.backup",
                statement=(
                    f"Independent Cargo Bay backup evidence requires review "
                    f"({backup_state})."
                ),
                status=ClaimStatus.CONFIRMED,
                confidence=Confidence.HIGH,
                evidence=(evidence,),
            )
        )

    for item in sorted(
        (
            value
            for value in _list(backup.get("items"))
            if isinstance(value, dict)
        ),
        key=lambda value: (
            _text(value.get("current_path")),
            _text(value.get("title")),
        ),
    ):
        current_path = _text(item.get("current_path"))
        cargo_id = cargo_by_path.get(current_path)
        if not current_path or not cargo_id:
            continue

        state = _text(item.get("state")) or "UNKNOWN"
        backup_id = f"backup:{current_path}"
        evidence = EvidenceRef(
            source="cargo_bay.backup",
            reference=current_path,
            summary=(
                f"Independent backup evidence for {current_path} is {state}"
            ),
        )
        if graph.node(backup_id) is None:
            graph.add_node(
                KnowledgeNode(
                    id=backup_id,
                    kind=NodeKind.BACKUP_EVIDENCE,
                    label=_text(item.get("title")) or current_path,
                    state=state,
                    attributes=_attributes(
                        current_path=current_path,
                        size_bytes=item.get("size_bytes"),
                        backed_up_at=item.get("backed_up_at"),
                        sha256=item.get("sha256"),
                    ),
                    evidence=(evidence,),
                )
            )
        graph.add_edge(
            KnowledgeEdge(
                source=cargo_id,
                target=backup_id,
                relation=Relation.EVIDENCED_BY,
                evidence=(evidence,),
            )
        )

    return cargo_by_path


def _impact_reports(
    graph: KnowledgeGraph,
    sources: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    reports = []

    for device, node_id in sorted(set(sources)):
        source_node = graph.node(node_id)
        if source_node is None:
            continue

        reachable = []
        for impact in graph.blast_radius(node_id):
            node = graph.node(impact.node_id)
            if node is None:
                continue
            reachable.append(
                {
                    "node_id": node.id,
                    "kind": node.kind.value,
                    "label": node.label,
                    "state": node.state,
                    "depth": impact.depth,
                    "via": list(impact.via),
                }
            )

        reports.append(
            {
                "source_node": node_id,
                "source_device": device,
                "known_downstream_count": len(reachable),
                "reachable": reachable,
            }
        )

    return reports


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
        state = _text(pool.get("health") or pool.get("state")) or None
        evidence = EvidenceRef(
            source="snapshot.storage",
            reference=f"storage.pools[{name}]",
            summary=f"Pool {name} observed with state {state or 'unknown'}",
        )
        _ensure_pool_node(
            graph,
            pool_ids,
            name=name,
            host_id=host_id,
            state=state,
            evidence=evidence,
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
                    remaining_redundancy=record.get("remaining_redundancy"),
                    vdev_topology=record.get("vdev_topology"),
                ),
                evidence=(disk_evidence,),
            )
        )

        bay = record.get("physical_bay")
        if bay not in (None, ""):
            bay_id = f"bay:{bay}"
            if graph.node(bay_id) is None:
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

        if pool and target_id is None:
            target_id = _ensure_pool_node(
                graph,
                pool_ids,
                name=pool,
                host_id=host_id,
                evidence=disk_evidence,
            )

        if pool and vdev and target_id:
            key = (pool, vdev)
            vdev_id = vdev_ids.setdefault(key, f"vdev:{pool}:{vdev}")
            if graph.node(vdev_id) is None:
                graph.add_node(
                    KnowledgeNode(
                        id=vdev_id,
                        kind=NodeKind.VDEV,
                        label=vdev,
                        attributes=_attributes(
                            topology=record.get("vdev_topology"),
                            remaining_redundancy=record.get("remaining_redundancy"),
                        ),
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

    smart_sources: list[tuple[str, str]] = []

    for record in _list(storage.get("smart")):
        if not isinstance(record, dict) or not _smart_actionable(record):
            continue

        device = _text(record.get("device") or record.get("drive")) or "unknown"
        disk_id = f"disk:{device}"
        smart_sources.append((device, disk_id))
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
        if graph.node(disk_id) is None:
            assessment.unknowns.append(
                f"SMART evidence exists for {device}, but current storage "
                "topology does not identify that device; downstream impact "
                "cannot be proven."
            )

    _add_topology(
        graph,
        assessment,
        _dict(payload.get("sentinel_topology")),
        pool_ids=pool_ids,
        host_id=host_id,
    )

    _add_cargo(
        graph,
        assessment,
        _dict(payload.get("cargo_bay")),
        pool_ids=pool_ids,
        host_id=host_id,
    )

    if assessment.claims:
        assessment.state = "REVIEW"

    return {
        "schema_version": 1,
        "read_only": True,
        "control_authority": False,
        "graph": graph.to_payload(),
        "assessment": assessment.to_payload(),
        "impact_reports": _impact_reports(graph, smart_sources),
    }
