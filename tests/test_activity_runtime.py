from truepanel.activity import ActivityProviderStatus, PlexActivityProvider
from truepanel.activity.runtime import (
    PLEX_TOKEN_FILE_ENV,
    PLEX_URL_ENV,
    activity_providers_from_environment,
)


def _token_file(tmp_path, *, mode=0o600):
    path = tmp_path / "plex-token"
    path.write_text("super-secret\n", encoding="utf-8")
    path.chmod(mode)
    return path


def test_activity_runtime_leaves_unconfigured_plex_disabled():
    assert activity_providers_from_environment({}) == ()


def test_activity_runtime_marks_partial_plex_configuration_unavailable(tmp_path):
    token_file = _token_file(tmp_path)
    providers = activity_providers_from_environment(
        {PLEX_TOKEN_FILE_ENV: str(token_file)}
    )

    assert len(providers) == 1
    snapshot = providers[0].snapshot()
    assert snapshot.source == "plex"
    assert snapshot.status is ActivityProviderStatus.UNAVAILABLE
    assert snapshot.observations == ()
    assert "super-secret" not in repr(snapshot.as_dict())


def test_activity_runtime_builds_plex_only_with_private_token_file(tmp_path):
    token_file = _token_file(tmp_path)
    providers = activity_providers_from_environment(
        {
            PLEX_URL_ENV: "http://127.0.0.1:32400",
            PLEX_TOKEN_FILE_ENV: str(token_file),
        }
    )

    assert len(providers) == 1
    assert isinstance(providers[0], PlexActivityProvider)
    assert providers[0].source == "plex"


def test_activity_runtime_rejects_group_or_world_readable_token_file(tmp_path):
    token_file = _token_file(tmp_path, mode=0o644)
    providers = activity_providers_from_environment(
        {
            PLEX_URL_ENV: "http://127.0.0.1:32400",
            PLEX_TOKEN_FILE_ENV: str(token_file),
        }
    )

    snapshot = providers[0].snapshot()
    assert snapshot.status is ActivityProviderStatus.UNAVAILABLE
    assert "super-secret" not in repr(snapshot.as_dict())


def test_activity_runtime_rejects_symlink_token_file(tmp_path):
    token_file = _token_file(tmp_path)
    link = tmp_path / "plex-token-link"
    link.symlink_to(token_file)
    providers = activity_providers_from_environment(
        {
            PLEX_URL_ENV: "http://127.0.0.1:32400",
            PLEX_TOKEN_FILE_ENV: str(link),
        }
    )

    assert providers[0].snapshot().status is ActivityProviderStatus.UNAVAILABLE


def test_activity_runtime_invalid_plex_url_fails_closed(tmp_path):
    token_file = _token_file(tmp_path)
    providers = activity_providers_from_environment(
        {
            PLEX_URL_ENV: "file:///tmp/plex",
            PLEX_TOKEN_FILE_ENV: str(token_file),
        }
    )

    assert len(providers) == 1
    snapshot = providers[0].snapshot()
    assert snapshot.status is ActivityProviderStatus.UNAVAILABLE
    assert "super-secret" not in repr(snapshot.as_dict())
