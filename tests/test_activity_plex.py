from urllib.request import Request

import pytest

from truepanel.activity import ActivityState, PlexActivityProvider, parse_plex_sessions


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


def test_parse_plex_sessions_normalizes_media_without_private_session_fields():
    activities = parse_plex_sessions(SESSIONS)

    assert len(activities) == 2
    episode = activities[0]
    assert episode.source == "plex"
    assert episode.state is ActivityState.PLAYING
    assert episode.title == "The Inner Light"
    assert episode.subtitle == "Star Trek: TNG · Season 5"
    assert episode.progress == 0.5
    assert episode.kind == "episode"

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

    activities = provider.snapshot()

    assert len(activities) == 2
    assert seen == {
        "url": "http://127.0.0.1:32400/status/sessions",
        "token": "super-secret",
        "timeout": 1.25,
    }
    assert "super-secret" not in str(seen["url"])


def test_progress_is_clamped_and_malformed_values_are_ignored():
    activities = parse_plex_sessions(
        """<MediaContainer>
        <Video title="Over" viewOffset="200" duration="100"><Player state="playing" /></Video>
        <Video title="Odd" viewOffset="wat" duration="100"><Player state="playing" /></Video>
        </MediaContainer>"""
    )
    assert activities[0].progress == 1.0
    assert activities[1].progress is None


def test_model_rejects_out_of_range_progress():
    from truepanel.activity.model import ActivityItem

    with pytest.raises(ValueError, match="progress"):
        ActivityItem("plex", ActivityState.ACTIVE, "Thing", progress=1.1)
