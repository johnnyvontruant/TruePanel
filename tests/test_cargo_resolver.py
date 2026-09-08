from pathlib import Path

from truepanel.cargo import CargoResolver, ServarrConfig

NOW = 1_788_894_000.0


class FakeClient:
    def __init__(self, config, responses):
        self.config = config
        self.responses = responses

    def get(self, endpoint, params=None):
        key = endpoint

        if endpoint == "/api/v3/history":
            key = "history"

        value = self.responses[key]

        if isinstance(value, Exception):
            raise value

        return value

    def optional_get(self, endpoint):
        return self.responses.get(endpoint, {})


def config(name, media_prefix, host_prefix):
    return ServarrConfig(
        name=name,
        base_url="http://127.0.0.1",
        config_path=Path("/unused/config.xml"),
        media_prefix=media_prefix,
        host_prefix=Path(host_prefix),
    )


def test_cargo_resolves_current_sonarr_file(tmp_path):
    shows = tmp_path / "Shows"
    target = shows / "TV N-Z" / "Vigil (2021)" / "3x04 - Episode 4.mkv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x" * 20)

    sonarr = FakeClient(
        config("sonarr", "/media/tv", shows),
        {
            "/api/v3/series": [
                {
                    "id": 324,
                    "title": "Vigil",
                    "path": "/media/tv/TV N-Z/Vigil (2021)",
                }
            ],
            "history": {
                "records": [
                    {
                        "id": 19,
                        "seriesId": 324,
                        "episodeId": 18551,
                        "eventType": "downloadFolderImported",
                        "date": "2026-09-08T17:05:09Z",
                        "data": {
                            "fileId": "14806",
                            "size": "20",
                            "importedPath": (
                                "/media/tv/TV N-Z/Vigil (2021)/"
                                "3x04 - Episode 4.mkv"
                            ),
                        },
                    }
                ]
            },
            "/api/v3/episode/18551": {
                "episodeFileId": 14806,
                "seasonNumber": 3,
                "episodeNumber": 4,
                "title": "Episode 4",
            },
            "/api/v3/episodefile/14806": {
                "relativePath": "3x04 - Episode 4.mkv",
            },
        },
    )

    radarr = FakeClient(
        config("radarr", "/media/movies", tmp_path / "Movies"),
        {
            "/api/v3/movie": [],
            "history": {"records": []},
        },
    )

    payload = CargoResolver(
        sonarr_client=sonarr,
        radarr_client=radarr,
        clock=lambda: NOW,
        window_seconds=10**9,
    ).snapshot()

    assert payload["state"] == "NOMINAL"
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["resolved"] == 1

    item = payload["groups"]["tv"][0]

    assert item["title"] == "Vigil"
    assert item["detail"] == "3x04 - Episode 4"
    assert item["resolution"] == "history-file-id"
    assert item["current_file_id"] == 14806
    assert item["exists"] is True
    assert item["size_bytes"] == 20


def test_cargo_falls_back_to_current_episode_file_id(tmp_path):
    shows = tmp_path / "Shows"
    target = shows / "TV N-Z" / "Scrubs (2026)" / "1x05 - My Angel.mkv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x" * 30)

    sonarr = FakeClient(
        config("sonarr", "/media/tv", shows),
        {
            "/api/v3/series": [
                {
                    "id": 50,
                    "title": "Scrubs (2026)",
                    "path": "/media/tv/TV N-Z/Scrubs (2026)",
                }
            ],
            "history": {
                "records": [
                    {
                        "id": 12,
                        "seriesId": 50,
                        "episodeId": 100,
                        "eventType": "downloadFolderImported",
                        "date": "2026-09-07T19:57:00Z",
                        "data": {
                            "fileId": "14635",
                            "size": "30",
                            "importedPath": (
                                "/media/tv/TV N-Z/Scrubs (2026)/"
                                "Season 1/old.mkv"
                            ),
                        },
                    }
                ]
            },
            "/api/v3/episode/100": {
                "episodeFileId": 14803,
                "seasonNumber": 1,
                "episodeNumber": 5,
                "title": "My Angel",
            },
            "/api/v3/episodefile/14803": {
                "relativePath": "1x05 - My Angel.mkv",
            },
        },
    )

    radarr = FakeClient(
        config("radarr", "/media/movies", tmp_path / "Movies"),
        {
            "/api/v3/movie": [],
            "history": {"records": []},
        },
    )

    payload = CargoResolver(
        sonarr_client=sonarr,
        radarr_client=radarr,
        clock=lambda: NOW,
        window_seconds=10**9,
    ).snapshot()

    item = payload["groups"]["tv"][0]

    assert item["history_file_id"] == 14635
    assert item["current_file_id"] == 14803
    assert item["resolution"] == "episode-current-file-id"
    assert item["moved_since_import"] is True
    assert item["exists"] is True


def test_cargo_tracks_radarr_movie_after_root_move(tmp_path):
    movies_root = tmp_path / "Movies"
    target = (
        movies_root
        / "Movies J-S"
        / "One Night Only (2026)"
        / "One Night Only (2026).mkv"
    )
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x" * 40)

    sonarr = FakeClient(
        config("sonarr", "/media/tv", tmp_path / "Shows"),
        {
            "/api/v3/series": [],
            "history": {"records": []},
        },
    )

    radarr = FakeClient(
        config("radarr", "/media/movies", movies_root),
        {
            "/api/v3/movie": [
                {
                    "id": 3804,
                    "title": "One Night Only",
                    "year": 2026,
                    "movieFileId": 3698,
                    "path": (
                        "/media/movies/Movies J-S/"
                        "One Night Only (2026)"
                    ),
                }
            ],
            "history": {
                "records": [
                    {
                        "id": 1375,
                        "movieId": 3804,
                        "eventType": "downloadFolderImported",
                        "date": "2026-09-08T17:10:39Z",
                        "data": {
                            "fileId": "3698",
                            "size": "40",
                            "importedPath": (
                                "/media/movies/Movies 1-D/"
                                "One Night Only (2026)/"
                                "One Night Only (2026).mkv"
                            ),
                        },
                    }
                ]
            },
            "/api/v3/moviefile/3698": {
                "relativePath": "One Night Only (2026).mkv",
            },
        },
    )

    payload = CargoResolver(
        sonarr_client=sonarr,
        radarr_client=radarr,
        clock=lambda: NOW,
        window_seconds=10**9,
    ).snapshot()

    item = payload["groups"]["movies"][0]

    assert item["title"] == "One Night Only (2026)"
    assert item["resolution"] == "history-file-id"
    assert item["moved_since_import"] is True
    assert item["exists"] is True
    assert "Movies J-S" in item["current_path"]


def test_unresolved_cargo_forces_review(tmp_path):
    sonarr = FakeClient(
        config("sonarr", "/media/tv", tmp_path / "Shows"),
        {
            "/api/v3/series": [
                {
                    "id": 1,
                    "title": "Missing Show",
                    "path": "/media/tv/TV A-M/Missing Show",
                }
            ],
            "history": {
                "records": [
                    {
                        "id": 1,
                        "seriesId": 1,
                        "episodeId": 2,
                        "eventType": "downloadFolderImported",
                        "date": "2026-09-08T17:00:00Z",
                        "data": {
                            "fileId": "999",
                            "size": "100",
                            "importedPath": "/media/tv/old.mkv",
                        },
                    }
                ]
            },
            "/api/v3/episode/2": {
                "seasonNumber": 1,
                "episodeNumber": 1,
                "title": "Missing",
            },
        },
    )

    radarr = FakeClient(
        config("radarr", "/media/movies", tmp_path / "Movies"),
        {
            "/api/v3/movie": [],
            "history": {"records": []},
        },
    )

    payload = CargoResolver(
        sonarr_client=sonarr,
        radarr_client=radarr,
        clock=lambda: NOW,
        window_seconds=10**9,
    ).snapshot()

    assert payload["state"] == "REVIEW"
    assert payload["summary"]["unresolved"] == 1
    assert payload["backup"] == {
        "tracking": False,
        "state": "NOT_TRACKED",
    }


def test_empty_cargo_is_clear(tmp_path):
    sonarr = FakeClient(
        config("sonarr", "/media/tv", tmp_path / "Shows"),
        {
            "/api/v3/series": [],
            "history": {"records": []},
        },
    )
    radarr = FakeClient(
        config("radarr", "/media/movies", tmp_path / "Movies"),
        {
            "/api/v3/movie": [],
            "history": {"records": []},
        },
    )

    payload = CargoResolver(
        sonarr_client=sonarr,
        radarr_client=radarr,
        clock=lambda: NOW,
    ).snapshot()

    assert payload["state"] == "CLEAR"
    assert payload["summary"]["total"] == 0
