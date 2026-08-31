from urllib.request import Request

import pytest

from truepanel.activity import (
    ActivityIntensity,
    ActivityObservation,
    ActivityProviderStatus,
    ActivitySnapshot,
    ActivityState,
    PlexActivityProvider,
    parse_plex_sessions,
)


SESSIONS = b"""\
<MediaContainer size="2">
  <Video type="episode" title="The Inner Light" grandparentTitle="Star Trek: TNG"
         parentTitle="Season 5" viewOffset="900000" duration="1800000">
    <Player state="playing" title="Living Room" />
    <User title="Picard" />
  </Video>
  <Video type="movie" title="Arrival" viewOffset="10" duration="100">
    <Player state="paused" title="Office" />
  </Video>
</MediaContainer>
"""


def test_observation_contract_is_versioned_and_presentation_neutral():
    observation = ActivityObservation(
        source="example",
        kind="maintenance",
        state=ActivityState.ACTIVE,
        title="Background maintenance",
        confidence=0.75,
        intensity=ActivityIntensity.MODERATE,
        context={"scope": "storage"},
        evidence=("host.signal",),
    )

    assert observation.as_dict() == {
        "schema_version": 1,
        "source": "example",
        "kind": "maintenance",
        "state": "active",
        "title": "Background maintenance",
        "confidence": 0.75,
        "intensity": "moderate",
        "subtitle": None,
        "progress": None,
        "started_at": None,
        "context": {"scope": "storage"},
        "evidence": ["host.signal"],
    }


def test_snapshot_rejects_cross_provider_evidence():
    observation = ActivityObservation(
        source="plex",
        kind="movie",
        state=ActivityState.PLAYING,
        title="Arrival",
    )

    with pytest.raises(ValueError, match="source"):
        ActivitySnapshot(
            source="zfs",
            status=ActivityProviderStatus.AVAILABLE,
            observations=(observation,),
        )


def test_parse_plex_sessions_normalizes_media_without_private_session_fields():
    activities = parse_plex_sessions(SESSIONS)

    assert len(activities) == 2
    episode = activities[0]
    assert episode.source == "plex"
    assert episode.state is ActivityState.PLAYING
    assert episode.intensity is ActivityIntensity.MODERATE
    assert episode.title == "The Inner Light"
    assert episode.subtitle == "Star Trek: TNG · Season 5"
    assert episode.progress == 0.5
    assert episode.kind == "episode"
    assert episode.evidence == ("plex.status.sessions",)

    payload = episode.as_dict()
    assert "Picard" not in repr(payload)
    assert "Living Room" not in repr(payload)


def test_provider_uses_header_token_and_never_places_it_in_url():
    seen: dict[str, object] = {}

    def fetch(request: Request, timeout: float) -> bytes:
        seen["url"] = request.full_url
        seen["token"] = request.get_header("X-plex-token")
        seen["timeout"] = timeout
        return SESSIONS

    provider = PlexActivityProvider(
        "http://127.0.0.1:32400/",
        "super-secret",
        timeout=1.25,
        fetcher=fetch,
    )

    snapshot = provider.snapshot()

    assert snapshot.status is ActivityProviderStatus.AVAILABLE
    assert len(snapshot.observations) == 2
    assert seen == {
        "url": "http://127.0.0.1:32400/status/sessions",
        "token": "super-secret",
        "timeout": 1.25,
    }
    assert "super-secret" not in str(seen["url"])
    assert "super-secret" not in repr(snapshot.as_dict())


def test_provider_failure_is_fail_closed_and_does_not_expose_exception_text():
    def fail(_request: Request, _timeout: float) -> bytes:
        raise OSError("super-secret transport failure")

    provider = PlexActivityProvider(
        "http://127.0.0.1:32400",
        "super-secret",
        fetcher=fail,
    )

    snapshot = provider.snapshot()

    assert snapshot.status is ActivityProviderStatus.UNAVAILABLE
    assert snapshot.observations == ()
    assert "super-secret" not in repr(snapshot.as_dict())


def test_progress_is_clamped_and_malformed_values_are_ignored():
    activities = parse_plex_sessions(
        """<MediaContainer>
        <Video title="Over" viewOffset="200" duration="100"><Player state="playing" /></Video>
        <Video title="Odd" viewOffset="wat" duration="100"><Player state="playing" /></Video>
        </MediaContainer>"""
    )
    assert activities[0].progress == 1.0
    assert activities[1].progress is None


def test_model_rejects_invalid_confidence_and_progress():
    with pytest.raises(ValueError, match="confidence"):
        ActivityObservation(
            "plex",
            "movie",
            ActivityState.ACTIVE,
            "Thing",
            confidence=1.1,
        )

    with pytest.raises(ValueError, match="progress"):
        ActivityObservation(
            "plex",
            "movie",
            ActivityState.ACTIVE,
            "Thing",
            progress=-0.1,
        )
