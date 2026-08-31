from truepanel.activity import ActivityProviderStatus, PlexActivityProvider
from truepanel.activity.runtime import (
    PLEX_TOKEN_ENV,
    PLEX_URL_ENV,
    activity_providers_from_environment,
)


def test_activity_runtime_leaves_unconfigured_plex_disabled():
    assert activity_providers_from_environment({}) == ()


def test_activity_runtime_marks_partial_plex_configuration_unavailable():
    providers = activity_providers_from_environment(
        {PLEX_TOKEN_ENV: "super-secret"}
    )

    assert len(providers) == 1
    snapshot = providers[0].snapshot()
    assert snapshot.source == "plex"
    assert snapshot.status is ActivityProviderStatus.UNAVAILABLE
    assert snapshot.observations == ()
    assert "super-secret" not in repr(snapshot.as_dict())


def test_activity_runtime_builds_plex_only_when_url_and_token_are_valid():
    providers = activity_providers_from_environment(
        {
            PLEX_URL_ENV: "http://127.0.0.1:32400",
            PLEX_TOKEN_ENV: "super-secret",
        }
    )

    assert len(providers) == 1
    assert isinstance(providers[0], PlexActivityProvider)
    assert providers[0].source == "plex"


def test_activity_runtime_invalid_plex_url_fails_closed():
    providers = activity_providers_from_environment(
        {
            PLEX_URL_ENV: "file:///tmp/plex",
            PLEX_TOKEN_ENV: "super-secret",
        }
    )

    assert len(providers) == 1
    snapshot = providers[0].snapshot()
    assert snapshot.status is ActivityProviderStatus.UNAVAILABLE
    assert "super-secret" not in repr(snapshot.as_dict())
