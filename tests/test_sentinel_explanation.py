from truepanel.sentinel import (
    LANGUAGE_GUARD,
    build_flight_director_explanation,
)


def _incident_package():
    return {
        "source_device": "/dev/sdc",
        "proved_blast_radius": [
            {
                "node_id": "cargo:radarr:77",
                "kind": "cargo",
                "label": "Example Movie",
                "state": "PRESENT",
                "depth": 5,
                "via": [
                    "disk:/dev/sdc",
                    "vdev:HDDs:raidz1-0",
                    "pool:HDDs",
                    "dataset:HDDs/Movies",
                    "application:radarr",
                    "cargo:radarr:77",
                ],
            },
            {
                "node_id": "vdev:HDDs:raidz1-0",
                "kind": "vdev",
                "label": "raidz1-0",
                "state": None,
                "depth": 1,
                "via": ["disk:/dev/sdc", "vdev:HDDs:raidz1-0"],
            },
            {
                "node_id": "backup:/mnt/HDDs/Movies/Example/movie.mkv",
                "kind": "backup_evidence",
                "label": "Example Movie backup evidence",
                "state": "VERIFIED",
                "depth": 6,
                "via": [
                    "disk:/dev/sdc",
                    "vdev:HDDs:raidz1-0",
                    "pool:HDDs",
                    "dataset:HDDs/Movies",
                    "application:radarr",
                    "cargo:radarr:77",
                    "backup:/mnt/HDDs/Movies/Example/movie.mkv",
                ],
            },
        ],
        "backup_evidence": [],
        "unknowns": ["Temperature correlation is unavailable."],
        "language_guard": LANGUAGE_GUARD,
    }


def _all_language(payload):
    parts = [payload["headline"], payload["summary"], payload["language_guard"]]
    parts.extend(payload["unknowns"])
    parts.extend(item["statement"] for item in payload["confirmed_facts"])
    parts.extend(item["statement"] for item in payload["protected_items"])
    return " ".join(parts).lower()


def test_explanation_is_deterministic_read_only_and_path_grounded():
    payload = build_flight_director_explanation(_incident_package())

    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["control_authority"] is False
    assert payload["state"] == "REVIEW"
    assert [item["node_id"] for item in payload["known_impact"]] == [
        "vdev:HDDs:raidz1-0",
        "cargo:radarr:77",
        "backup:/mnt/HDDs/Movies/Example/movie.mkv",
    ]
    assert all(
        item["provenance"]["type"] == "proved_graph_path"
        for item in payload["confirmed_facts"]
    )
    assert payload["confirmed_facts"][0]["provenance"]["path"] == [
        "disk:/dev/sdc",
        "vdev:HDDs:raidz1-0",
    ]
    assert payload["recovery"]["available"] is False
    assert payload["recovery"]["authority"] is False


def test_verified_backup_evidence_becomes_protected_item_only_when_proved():
    payload = build_flight_director_explanation(_incident_package())

    assert payload["protected_items"] == [
        {
            "node_id": "backup:/mnt/HDDs/Movies/Example/movie.mkv",
            "label": "Example Movie backup evidence",
            "state": "VERIFIED",
            "statement": (
                "Verified independent backup evidence is reachable for "
                "Example Movie backup evidence."
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


def test_nonverified_backup_evidence_is_not_described_as_protected():
    incident = _incident_package()
    incident["proved_blast_radius"][-1]["state"] = "UNKNOWN"

    payload = build_flight_director_explanation(incident)

    assert payload["protected_items"] == []
    assert "unprotected" not in _all_language(payload)


def test_language_never_promotes_absence_to_unaffected():
    payload = build_flight_director_explanation(_incident_package())

    language = _all_language(payload)
    assert "plex" not in language
    assert "unaffected" in payload["language_guard"].lower()
    assert "classified as unaffected" in payload["summary"].lower()
    assert "plex is unaffected" not in language


def test_missing_source_fails_closed_and_discards_impact_claims():
    incident = _incident_package()
    incident["source_device"] = ""

    payload = build_flight_director_explanation(incident)

    assert payload["state"] == "HOLD"
    assert payload["known_impact"] == []
    assert payload["confirmed_facts"] == []
    assert any("source" in item.lower() for item in payload["unknowns"])


def test_malformed_paths_fail_closed_instead_of_being_repaired():
    incident = _incident_package()
    incident["proved_blast_radius"] = [
        {
            "node_id": "application:radarr",
            "kind": "application",
            "label": "Radarr",
            "depth": 4,
            "via": [],
        }
    ]

    payload = build_flight_director_explanation(incident)

    assert payload["state"] == "HOLD"
    assert payload["known_impact"] == []
    assert any("no valid proved graph path" in item.lower() for item in payload["unknowns"])


def test_output_is_stable_when_incident_items_arrive_in_different_order():
    incident = _incident_package()
    reversed_incident = _incident_package()
    reversed_incident["proved_blast_radius"] = list(
        reversed(reversed_incident["proved_blast_radius"])
    )
    reversed_incident["unknowns"] = list(reversed(reversed_incident["unknowns"]))

    assert build_flight_director_explanation(incident) == (
        build_flight_director_explanation(reversed_incident)
    )
