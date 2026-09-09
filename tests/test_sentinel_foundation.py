import pytest

from truepanel.sentinel import (
    EvidenceRef,
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    NodeKind,
    Relation,
    build_sentinel_snapshot,
)


def empty_topology():
    return {
        "schema_version": 1,
        "read_only": True,
        "datasets": [],
        "applications": [],
        "relationships": [],
    }


def test_graph_blast_radius_is_deterministic_and_cycle_safe():
    graph = KnowledgeGraph()
    evidence = EvidenceRef(
        source="fixture",
        reference="disk-1",
        summary="fixture relationship",
    )

    for node in (
        KnowledgeNode("disk:sda", NodeKind.DISK, "sda"),
        KnowledgeNode("vdev:tank:0", NodeKind.VDEV, "raidz1-0"),
        KnowledgeNode("pool:tank", NodeKind.POOL, "tank"),
        KnowledgeNode("cargo:radarr:7", NodeKind.CARGO, "Movie"),
    ):
        graph.add_node(node)

    graph.add_edge(
        KnowledgeEdge(
            "pool:tank",
            "cargo:radarr:7",
            Relation.SERVES,
            (evidence,),
        )
    )
    graph.add_edge(
        KnowledgeEdge(
            "disk:sda",
            "vdev:tank:0",
            Relation.MEMBER_OF,
            (evidence,),
        )
    )
    graph.add_edge(
        KnowledgeEdge(
            "vdev:tank:0",
            "pool:tank",
            Relation.MEMBER_OF,
            (evidence,),
        )
    )
    graph.add_edge(
        KnowledgeEdge(
            "cargo:radarr:7",
            "pool:tank",
            Relation.MEMBER_OF,
            (evidence,),
        )
    )

    assert [item.node_id for item in graph.blast_radius("disk:sda")] == [
        "vdev:tank:0",
        "pool:tank",
        "cargo:radarr:7",
    ]


def test_graph_rejects_unproven_edge_targets():
    graph = KnowledgeGraph()
    graph.add_node(KnowledgeNode("disk:sda", NodeKind.DISK, "sda"))

    with pytest.raises(ValueError, match="missing node"):
        graph.add_edge(
            KnowledgeEdge(
                "disk:sda",
                "pool:missing",
                Relation.MEMBER_OF,
            )
        )


def test_runtime_links_storage_to_cargo_and_preserves_provenance():
    payload = {
        "system": {"hostname": "BattleStation"},
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "devices": [
                {
                    "device": "/dev/sdc",
                    "pool": "HDDs",
                    "vdev": "raidz1-0",
                    "physical_bay": 3,
                    "zfs_state": "ONLINE",
                }
            ],
            "smart": [],
        },
        "sentinel_topology": empty_topology(),
        "cargo_bay": {
            "summary": {"unresolved": 0},
            "backup": {"tracking": False, "state": "NOT_TRACKED"},
            "groups": {
                "tv": [],
                "movies": [
                    {
                        "source": "radarr",
                        "history_id": 77,
                        "title": "Example Movie",
                        "current_path": "/mnt/HDDs/Movies/Example/movie.mkv",
                        "exists": True,
                        "resolution": "movie-current-file-id",
                        "imported_at": 123.0,
                    }
                ],
            },
        },
    }

    sentinel = build_sentinel_snapshot(payload)

    assert sentinel["read_only"] is True
    assert sentinel["control_authority"] is False

    graph = sentinel["graph"]
    node_ids = {node["id"] for node in graph["nodes"]}
    assert {
        "hardware:host",
        "bay:3",
        "disk:/dev/sdc",
        "vdev:HDDs:raidz1-0",
        "pool:HDDs",
        "application:radarr",
        "cargo:radarr:77",
    } <= node_ids

    edges = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in graph["edges"]
    }
    assert (
        "pool:HDDs",
        "cargo:radarr:77",
        "serves",
    ) in edges

    cargo_node = next(
        node for node in graph["nodes"] if node["id"] == "cargo:radarr:77"
    )
    assert cargo_node["evidence"][0]["source"] == "cargo_bay"
    assert "cannot infer" in sentinel["assessment"]["unknowns"][0]


def test_runtime_reports_actionable_smart_without_inventing_cause():
    sentinel = build_sentinel_snapshot(
        {
            "system": {"hostname": "BattleStation"},
            "storage": {
                "pools": [{"name": "HDDs", "health": "ONLINE"}],
                "devices": [],
                "smart": [
                    {
                        "device": "/dev/sdc",
                        "health": "FAILED",
                        "pending": 2,
                    }
                ],
            },
        }
    )

    assessment = sentinel["assessment"]
    assert assessment["state"] == "REVIEW"
    assert assessment["claims"] == [
        {
            "id": "storage.smart:/dev/sdc",
            "statement": "/dev/sdc has actionable SMART evidence.",
            "status": "confirmed",
            "confidence": "high",
            "evidence": [
                {
                    "source": "snapshot.storage.smart",
                    "reference": "/dev/sdc",
                    "summary": "Actionable SMART evidence observed for /dev/sdc",
                }
            ],
        }
    ]
    assert sentinel["impact_reports"] == []
    assert any(
        "downstream impact cannot be proven" in unknown
        for unknown in assessment["unknowns"]
    )


def test_runtime_marks_missing_backup_observation_unknown_not_unprotected():
    sentinel = build_sentinel_snapshot(
        {
            "sentinel_topology": empty_topology(),
            "cargo_bay": {
                "summary": {"unresolved": 0},
                "groups": {"tv": [], "movies": []},
                "backup": {"tracking": False, "state": "NOT_TRACKED"},
            },
        }
    )

    assessment = sentinel["assessment"]
    assert assessment["claims"] == []
    assert len(assessment["unknowns"]) == 1
    assert "protected or unprotected" in assessment["unknowns"][0]


def test_storage_intelligence_builds_full_consequence_chain():
    path = "/mnt/HDDs/Movies/Example/movie.mkv"
    sentinel = build_sentinel_snapshot(
        {
            "system": {"hostname": "BattleStation"},
            "storage": {
                "pools": [{"name": "HDDs", "health": "DEGRADED"}],
                "devices": [
                    {
                        "device": "/dev/sdc",
                        "pool": "HDDs",
                        "vdev": "raidz1-0",
                        "physical_bay": 3,
                        "zfs_state": "DEGRADED",
                        "remaining_redundancy": 0,
                        "vdev_topology": "raidz1",
                    }
                ],
                "smart": [
                    {
                        "device": "/dev/sdc",
                        "health": "FAILED",
                        "pending": 1,
                    }
                ],
            },
            "sentinel_topology": {
                "schema_version": 1,
                "read_only": True,
                "datasets": [
                    {
                        "id": "HDDs/Movies",
                        "name": "Movies",
                        "pool": "HDDs",
                        "type": "FILESYSTEM",
                        "mountpoint": "/mnt/HDDs/Movies",
                        "locked": False,
                    }
                ],
                "applications": [
                    {
                        "id": "radarr",
                        "name": "Radarr",
                        "state": "RUNNING",
                        "paths": ["/mnt/HDDs/Movies"],
                    }
                ],
                "relationships": [
                    {
                        "dataset_id": "HDDs/Movies",
                        "application_id": "radarr",
                        "path": "/mnt/HDDs/Movies",
                        "source": "truenas.app.query.literal_path",
                    }
                ],
            },
            "cargo_bay": {
                "summary": {"unresolved": 0},
                "groups": {
                    "tv": [],
                    "movies": [
                        {
                            "source": "radarr",
                            "history_id": 77,
                            "title": "Example Movie",
                            "current_path": path,
                            "exists": True,
                            "resolution": "movie-current-file-id",
                            "imported_at": 123.0,
                        }
                    ],
                },
                "backup": {
                    "tracking": True,
                    "state": "VERIFIED",
                    "items": [
                        {
                            "title": "Example Movie",
                            "current_path": path,
                            "state": "VERIFIED",
                            "size_bytes": 1000,
                            "backed_up_at": "2026-09-09T01:02:03Z",
                        }
                    ],
                },
            },
        }
    )

    edges = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in sentinel["graph"]["edges"]
    }
    assert (
        "pool:HDDs",
        "dataset:HDDs/Movies",
        "serves",
    ) in edges
    assert (
        "dataset:HDDs/Movies",
        "application:radarr",
        "serves",
    ) in edges
    assert (
        "application:radarr",
        "cargo:radarr:77",
        "produces",
    ) in edges
    assert (
        "cargo:radarr:77",
        f"backup:{path}",
        "evidenced_by",
    ) in edges

    report = sentinel["impact_reports"][0]
    assert report["source_node"] == "disk:/dev/sdc"
    impacted = {item["node_id"] for item in report["reachable"]}
    assert {
        "vdev:HDDs:raidz1-0",
        "pool:HDDs",
        "dataset:HDDs/Movies",
        "application:radarr",
        "cargo:radarr:77",
        f"backup:{path}",
    } <= impacted

    backup_node = next(
        node
        for node in sentinel["graph"]["nodes"]
        if node["id"] == f"backup:{path}"
    )
    assert backup_node["state"] == "VERIFIED"
