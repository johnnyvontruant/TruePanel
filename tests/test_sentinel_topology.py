import json
import subprocess

from truepanel.sentinel.topology import (
    CachedTopologyProvider,
    MidcltClient,
    TopologyResolver,
)


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, method, *arguments):
        self.calls.append((method, arguments))
        return self.responses[method]


def test_midclt_client_uses_supported_read_only_call_shape():
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps([{"id": "HDDs/Movies"}]),
            stderr="",
        )

    client = MidcltClient(runner=runner, timeout=3.0)
    result = client.call(
        "pool.dataset.query",
        [],
        {"extra": {"flat": True}},
    )

    assert result == [{"id": "HDDs/Movies"}]
    assert captured["command"] == [
        "midclt",
        "call",
        "pool.dataset.query",
        "[]",
        '{"extra":{"flat":true}}',
    ]
    assert captured["kwargs"]["check"] is True
    assert captured["kwargs"]["timeout"] == 3.0


def test_topology_resolver_uses_supported_plain_app_query_shape():
    client = FakeClient(
        {
            "pool.dataset.query": [],
            "app.query": [],
        }
    )

    TopologyResolver(client).snapshot()

    assert ("app.query", ([],)) in client.calls
    assert not any(
        method == "app.query" and len(arguments) > 1
        for method, arguments in client.calls
    )


def test_topology_resolver_maps_literal_app_path_to_nearest_dataset():
    client = FakeClient(
        {
            "pool.dataset.query": [
                {
                    "id": "HDDs",
                    "name": "HDDs",
                    "pool": "HDDs",
                    "type": "FILESYSTEM",
                    "mountpoint": {"value": "/mnt/HDDs"},
                    "locked": False,
                },
                {
                    "id": "HDDs/Movies",
                    "name": "Movies",
                    "pool": "HDDs",
                    "type": "FILESYSTEM",
                    "mountpoint": {"value": "/mnt/HDDs/Movies"},
                    "locked": False,
                },
            ],
            "app.query": [
                {
                    "id": "plex",
                    "name": "Plex",
                    "state": "RUNNING",
                    "config": {
                        "storage": {
                            "movies": {
                                "host_path": "/mnt/HDDs/Movies",
                            }
                        }
                    },
                }
            ],
        }
    )

    payload = TopologyResolver(client).snapshot()

    assert payload["read_only"] is True
    assert payload["source"] == "truenas.middleware"
    assert payload["applications"] == [
        {
            "id": "plex",
            "name": "Plex",
            "state": "RUNNING",
            "paths": ["/mnt/HDDs/Movies"],
        }
    ]
    assert payload["relationships"] == [
        {
            "dataset_id": "HDDs/Movies",
            "application_id": "plex",
            "path": "/mnt/HDDs/Movies",
            "mountpoint": "/mnt/HDDs/Movies",
            "source": "truenas.app.query.literal_path",
        }
    ]


def test_topology_resolver_does_not_guess_relationship_from_app_name():
    client = FakeClient(
        {
            "pool.dataset.query": [
                {
                    "id": "HDDs/Movies",
                    "name": "Movies",
                    "pool": "HDDs",
                    "type": "FILESYSTEM",
                    "mountpoint": {"value": "/mnt/HDDs/Movies"},
                }
            ],
            "app.query": [
                {
                    "id": "plex",
                    "name": "Plex Movies Server",
                    "state": "RUNNING",
                    "config": {"note": "Movies"},
                }
            ],
        }
    )

    payload = TopologyResolver(client).snapshot()

    assert payload["relationships"] == []


def test_topology_resolver_ignores_non_mnt_strings():
    client = FakeClient(
        {
            "pool.dataset.query": [],
            "app.query": [
                {
                    "id": "example",
                    "name": "Example",
                    "state": "RUNNING",
                    "config": {
                        "url": "https://example.test/mnt/HDDs/Movies",
                        "container_path": "/media/movies",
                    },
                }
            ],
        }
    )

    payload = TopologyResolver(client).snapshot()

    assert payload["applications"][0]["paths"] == []
    assert payload["relationships"] == []


def test_cached_topology_provider_bounds_calls_and_returns_copy():
    class Resolver:
        def __init__(self):
            self.calls = 0

        def snapshot(self):
            self.calls += 1
            return {
                "schema_version": 1,
                "read_only": True,
                "datasets": [{"id": "HDDs"}],
                "applications": [],
                "relationships": [],
            }

    resolver = Resolver()
    times = iter([10.0, 20.0, 80.0])
    provider = CachedTopologyProvider(
        resolver,
        cache_seconds=60.0,
        clock=lambda: next(times),
    )

    first = provider.snapshot()
    first["datasets"].append({"id": "mutated"})
    second = provider.snapshot()
    third = provider.snapshot()

    assert resolver.calls == 2
    assert second["datasets"] == [{"id": "HDDs"}]
    assert third["datasets"] == [{"id": "HDDs"}]
