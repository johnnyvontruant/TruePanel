from truepanel.web.sentinel_snapshot import SentinelSnapshotService


def _impact(
    node_id: str,
    kind: str,
    label: str,
    depth: int,
    via: list[str],
    *,
    state: str | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "kind": kind,
        "label": label,
        "state": state,
        "depth": depth,
        "via": via,
    }


def test_live_explanation_preserves_proved_paths_and_verified_backup():
    source = "/dev/sdc"
    sentinel = {
        "assessment": {"state": "REVIEW", "claims": [], "unknowns": []},
        "impact_reports": [
            {
                "source_device": source,
                "source_node_id": "disk:/dev/sdc",
                "state": "REVIEW",
                "known_downstream_count": 3,
                "reachable": [
                    _impact(
                        "pool:HDDs",
                        "pool",
                        "HDDs",
                        2,
                        ["disk:/dev/sdc", "vdev:HDDs:raidz1-0", "pool:HDDs"],
                        state="ONLINE",
                    ),
                    _impact(
                        "cargo:radarr:77",
                        "cargo",
                        "Example Movie",
                        5,
                        [
                            "disk:/dev/sdc",
                            "vdev:HDDs:raidz1-0",
                            "pool:HDDs",
                            "dataset:HDDs/Movies",
                            "application:radarr",
                            "cargo:radarr:77",
                        ],
                        state="PRESENT",
                    ),
                    _impact(
                        "backup:/mnt/HDDs/Movies/Example/movie.mkv",
                        "backup_evidence",
                        "Example Movie",
                        6,
                        [
                            "disk:/dev/sdc",
                            "vdev:HDDs:raidz1-0",
                            "pool:HDDs",
                            "dataset:HDDs/Movies",
                            "application:radarr",
                            "cargo:radarr:77",
                            "backup:/mnt/HDDs/Movies/Example/movie.mkv",
                        ],
                        state="VERIFIED",
                    ),
                ],
            }
        ],
    }

    SentinelSnapshotService._attach_live_explanations(sentinel)

    explanation = sentinel["explanations"][0]
    assert explanation["state"] == "REVIEW"
    assert explanation["read_only"] is True
    assert explanation["control_authority"] is False
    assert explanation["source_device"] == source
    assert len(explanation["known_impact"]) == 3
    assert explanation["known_impact"][1]["via"][-1] == "cargo:radarr:77"
    assert explanation["protected_items"] == [
        {
            "node_id": "backup:/mnt/HDDs/Movies/Example/movie.mkv",
            "label": "Example Movie",
            "state": "VERIFIED",
            "statement": (
                "Verified independent backup evidence is reachable for "
                "Example Movie."
            ),
            "provenance": {
                "type": "proved_graph_path",
                "path": [
                    "disk:/dev/sdc",
                    "vdev:HDDs:raidz1-0",
                    "pool:HDDs",
                    "dataset:HDDs/Movies",
                    "application:radarr",
                    "cargo:radarr:77",
                    "backup:/mnt/HDDs/Movies/Example/movie.mkv",
                ],
            },
        }
    ]


def test_no_impact_report_is_standby_not_synthetic_all_clear():
    sentinel = {
        "assessment": {
            "state": "CLEAR",
            "claims": [],
            "unknowns": ["Backup evidence is not available."],
        },
        "impact_reports": [],
    }

    SentinelSnapshotService._attach_live_explanations(sentinel)

    assert sentinel["explanations"] == []


def test_live_explanations_are_deterministically_sorted_by_source_device():
    sentinel = {
        "assessment": {"state": "REVIEW", "claims": [], "unknowns": []},
        "impact_reports": [
            {
                "source_device": "/dev/sdz",
                "source_node_id": "disk:/dev/sdz",
                "reachable": [
                    _impact(
                        "pool:Z",
                        "pool",
                        "Z",
                        1,
                        ["disk:/dev/sdz", "pool:Z"],
                    )
                ],
            },
            {
                "source_device": "/dev/sda",
                "source_node_id": "disk:/dev/sda",
                "reachable": [
                    _impact(
                        "pool:A",
                        "pool",
                        "A",
                        1,
                        ["disk:/dev/sda", "pool:A"],
                    )
                ],
            },
        ],
    }

    SentinelSnapshotService._attach_live_explanations(sentinel)

    assert [
        explanation["source_device"] for explanation in sentinel["explanations"]
    ] == ["/dev/sda", "/dev/sdz"]


def test_live_explanation_carries_topology_unknown_without_promoting_it():
    unknown = (
        "TrueNAS dataset/application topology evidence is unavailable; "
        "SENTINEL cannot prove dataset-to-application dependencies."
    )
    sentinel = {
        "assessment": {"state": "REVIEW", "claims": [], "unknowns": [unknown]},
        "impact_reports": [
            {
                "source_device": "/dev/sdc",
                "source_node_id": "disk:/dev/sdc",
                "reachable": [
                    _impact(
                        "pool:HDDs",
                        "pool",
                        "HDDs",
                        1,
                        ["disk:/dev/sdc", "pool:HDDs"],
                    )
                ],
            }
        ],
    }

    SentinelSnapshotService._attach_live_explanations(sentinel)

    explanation = sentinel["explanations"][0]
    assert explanation["unknowns"] == [unknown]
    assert "unaffected" in explanation["language_guard"]
    assert explanation["recovery"]["authority"] is False
