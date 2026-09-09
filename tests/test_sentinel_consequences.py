from truepanel.sentinel import (
    attach_consequence_summaries,
    summarize_consequences,
)


def _impact(node_id, kind, label, depth, *, state=None):
    return {
        "node_id": node_id,
        "kind": kind,
        "label": label,
        "state": state,
        "depth": depth,
        "via": ["disk:/dev/sdc", node_id],
    }


def test_consequence_summary_groups_only_proved_impact_objects():
    explanation = {
        "source_device": "/dev/sdc",
        "known_impact": [
            _impact("pool:HDDs", "pool", "HDDs", 2, state="ONLINE"),
            _impact(
                "dataset:HDDs/Movies",
                "dataset",
                "Movies",
                3,
            ),
            _impact(
                "application:radarr",
                "application",
                "Radarr",
                4,
                state="RUNNING",
            ),
            _impact(
                "cargo:radarr:77",
                "cargo",
                "Example Movie",
                5,
                state="PRESENT",
            ),
            _impact(
                "backup:/mnt/HDDs/Movies/Example/movie.mkv",
                "backup_evidence",
                "Example Movie",
                6,
                state="VERIFIED",
            ),
        ],
    }

    summary = summarize_consequences(explanation)

    assert summary["read_only"] is True
    assert summary["control_authority"] is False
    assert summary["source_device"] == "/dev/sdc"
    assert summary["counts"] == {
        "proved_objects": 5,
        "storage_objects": 2,
        "applications": 1,
        "running_applications": 1,
        "cargo": 1,
        "backup_evidence": 1,
    }
    assert [item["node_id"] for item in summary["applications"]] == [
        "application:radarr"
    ]
    assert "does not prove an outage" in summary["language_guard"]


def test_running_application_is_not_reclassified_as_down_or_unavailable():
    summary = summarize_consequences(
        {
            "source_device": "/dev/sdc",
            "known_impact": [
                _impact(
                    "application:plex",
                    "application",
                    "Plex",
                    3,
                    state="RUNNING",
                )
            ],
        }
    )

    assert summary["counts"]["running_applications"] == 1
    assert summary["applications"][0]["state"] == "RUNNING"
    assert "outage" in summary["language_guard"]
    assert "interruption" in summary["language_guard"]


def test_unproved_objects_cannot_enter_consequence_summary():
    summary = summarize_consequences(
        {
            "source_device": "/dev/sdc",
            "known_impact": [],
            "unaffected": [
                {
                    "node_id": "application:plex",
                    "kind": "application",
                    "state": "RUNNING",
                }
            ],
        }
    )

    assert summary["counts"]["proved_objects"] == 0
    assert summary["applications"] == []


def test_malformed_depth_does_not_take_sentinel_offline():
    summary = summarize_consequences(
        {
            "source_device": "/dev/sdc",
            "known_impact": [
                _impact("application:radarr", "application", "Radarr", "unknown"),
                _impact("pool:HDDs", "pool", "HDDs", 2),
            ],
        }
    )

    assert summary["counts"]["proved_objects"] == 2
    assert summary["applications"][0]["node_id"] == "application:radarr"


def test_attach_adds_summary_without_changing_recovery_contract():
    sentinel = {
        "explanations": [
            {
                "source_device": "/dev/sdc",
                "known_impact": [
                    _impact(
                        "application:radarr",
                        "application",
                        "Radarr",
                        4,
                        state="RUNNING",
                    )
                ],
                "recovery": {
                    "available": True,
                    "authority": False,
                    "references": [{"code": "storage.smart_warning"}],
                },
            }
        ]
    }

    attach_consequence_summaries(sentinel)

    explanation = sentinel["explanations"][0]
    assert explanation["consequences"]["counts"]["applications"] == 1
    assert explanation["recovery"] == {
        "available": True,
        "authority": False,
        "references": [{"code": "storage.smart_warning"}],
    }
