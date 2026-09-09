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


def test_runtime_marks_missing_backup_observation_unknown_not_unprotected():
    sentinel = build_sentinel_snapshot(
        {
            "cargo_bay": {
                "summary": {"unresolved": 0},
                "groups": {"tv": [], "movies": []},
                "backup": {"tracking": False, "state": "NOT_TRACKED"},
            }
        }
    )

    assessment = sentinel["assessment"]
    assert assessment["claims"] == []
    assert len(assessment["unknowns"]) == 1
    assert "protected or unprotected" in assessment["unknowns"][0]
