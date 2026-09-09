from pathlib import Path

import yaml

from truepanel.sentinel.rehearsal import run_sentinel_rehearsal


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "scenarios"
    / "sentinel-bay3-storage-impact.yaml"
)


def load_fixture():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def test_bay3_rehearsal_proves_storage_application_cargo_backup_chain():
    result = run_sentinel_rehearsal(load_fixture())

    assert result["passed"] is True
    assert result["read_only"] is True
    assert result["control_authority"] is False

    incident = result["incident_package"]
    assert incident["source_device"] == "/dev/sdc"

    reachable = {
        item["node_id"]
        for item in incident["proved_blast_radius"]
    }
    assert {
        "vdev:HDDs:raidz1-0",
        "pool:HDDs",
        "dataset:HDDs/Movies",
        "application:radarr",
        "cargo:radarr:77",
        "backup:/mnt/HDDs/Movies/Example Movie (2026)/movie.mkv",
    } <= reachable

    assert incident["backup_evidence"] == [
        next(
            item
            for item in incident["proved_blast_radius"]
            if item["node_id"].startswith("backup:")
        )
    ]
    assert incident["backup_evidence"][0]["state"] == "VERIFIED"


def test_bay3_rehearsal_does_not_invent_unrelated_plex_impact():
    result = run_sentinel_rehearsal(load_fixture())

    reachable = {
        item["node_id"]
        for item in result["incident_package"]["proved_blast_radius"]
    }
    assert "pool:SSDs" not in reachable
    assert "dataset:SSDs/Applications" not in reachable
    assert "application:plex" not in reachable
    assert "not automatically classified as unaffected" in (
        result["incident_package"]["language_guard"]
    )


def test_rehearsal_fails_if_expected_evidence_disappears():
    document = load_fixture()
    document["snapshot"]["cargo_bay"]["backup"]["items"] = []

    result = run_sentinel_rehearsal(document)

    assert result["passed"] is False
    failed = {
        item["name"]
        for item in result["checks"]
        if item["passed"] is False
    }
    assert (
        "reachable:backup:/mnt/HDDs/Movies/Example Movie (2026)/movie.mkv"
        in failed
    )
    assert (
        "state:backup:/mnt/HDDs/Movies/Example Movie (2026)/movie.mkv"
        in failed
    )


def test_rehearsal_fails_if_unrelated_application_enters_blast_radius():
    document = load_fixture()
    document["snapshot"]["sentinel_topology"]["relationships"].append(
        {
            "dataset_id": "HDDs/Movies",
            "application_id": "plex",
            "path": "/mnt/HDDs/Movies",
            "source": "test.invalid-proof",
        }
    )

    result = run_sentinel_rehearsal(document)

    assert result["passed"] is False
    failed = {
        item["name"]
        for item in result["checks"]
        if item["passed"] is False
    }
    assert "not-in-proved-blast-radius:application:plex" in failed
