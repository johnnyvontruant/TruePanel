from truepanel.cargo import (
    CachedCargoProvider,
    provider_from_config,
)


class Resolver:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {
            "schema_version": 1,
            "read_only": True,
            "state": "CLEAR",
        }
        self.error = error
        self.calls = 0

    def snapshot(self):
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.payload


def test_cached_provider_uses_one_resolver_call_inside_ttl():
    now = [100.0]
    resolver = Resolver(
        {
            "schema_version": 1,
            "read_only": True,
            "state": "NOMINAL",
        }
    )

    provider = CachedCargoProvider(
        resolver,
        cache_seconds=60,
        clock=lambda: now[0],
    )

    first = provider.snapshot()
    second = provider.snapshot()

    assert first == second
    assert resolver.calls == 1


def test_cached_provider_refreshes_after_ttl():
    now = [100.0]
    resolver = Resolver()

    provider = CachedCargoProvider(
        resolver,
        cache_seconds=60,
        clock=lambda: now[0],
    )

    provider.snapshot()

    now[0] = 159.9
    provider.snapshot()
    assert resolver.calls == 1

    now[0] = 160.0
    provider.snapshot()
    assert resolver.calls == 2


def test_cached_provider_does_not_hide_refresh_failure():
    now = [100.0]
    resolver = Resolver()

    provider = CachedCargoProvider(
        resolver,
        cache_seconds=60,
        clock=lambda: now[0],
    )

    provider.snapshot()

    resolver.error = OSError("Sonarr unavailable")
    now[0] = 161.0

    try:
        provider.snapshot()
    except OSError:
        pass
    else:
        raise AssertionError("refresh failure must escape provider")


def test_disabled_configuration_builds_no_provider():
    provider = provider_from_config(
        {
            "mission_control": {
                "cargo_bay": {
                    "enabled": False,
                }
            }
        }
    )

    assert provider is None


def test_enabled_configuration_requires_complete_endpoints():
    provider = provider_from_config(
        {
            "mission_control": {
                "cargo_bay": {
                    "enabled": True,
                    "sonarr": {},
                    "radarr": {},
                }
            }
        }
    )

    assert provider is None


def test_enabled_configuration_builds_portable_provider():
    provider = provider_from_config(
        {
            "mission_control": {
                "cargo_bay": {
                    "enabled": True,
                    "window_seconds": 43200,
                    "cache_seconds": 45,
                    "history_limit": 99,
                    "sonarr": {
                        "url": "http://sonarr:8989",
                        "config_path": "/config/sonarr.xml",
                        "media_prefix": "/tv",
                        "host_prefix": "/tank/shows",
                    },
                    "radarr": {
                        "url": "http://radarr:7878",
                        "config_path": "/config/radarr.xml",
                        "media_prefix": "/movies",
                        "host_prefix": "/tank/movies",
                    },
                }
            }
        },
        cache_clock=lambda: 1.0,
        resolver_clock=lambda: 2.0,
    )

    assert isinstance(provider, CachedCargoProvider)
    assert provider.cache_seconds == 45

    resolver = provider.resolver

    assert resolver.window_seconds == 43200
    assert resolver.history_limit == 99

    assert (
        resolver.sonarr_client.config.base_url
        == "http://sonarr:8989"
    )
    assert (
        str(resolver.sonarr_client.config.host_prefix)
        == "/tank/shows"
    )
    assert (
        resolver.radarr_client.config.base_url
        == "http://radarr:7878"
    )
