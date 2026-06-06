from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_mock_html
from yt_meta import VideoUnavailableError
from yt_meta.fetchers import VideoFetcher


def _video_fetcher_returning(player_response, initial_data=None):
    """A VideoFetcher whose session returns a mock watch page built from
    the given player_response / initial_data."""
    if initial_data is None:
        initial_data = {
            "contents": {},
            "frameworkUpdates": {"entityBatchUpdate": {"mutations": []}},
        }
    session = MagicMock()
    response = MagicMock()
    response.text = make_mock_html(player_response, initial_data)
    response.raise_for_status = MagicMock()
    session.get.return_value = response
    return VideoFetcher(session=session, cache={})


_OK_PLAYER = {
    "playabilityStatus": {"status": "OK"},
    "videoDetails": {
        "videoId": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "author": "Rick Astley",
        "lengthSeconds": "212",
        "viewCount": "1000",
    },
    "microformat": {"playerMicroformatRenderer": {"publishDate": "2009-10-25"}},
}
_DELETED_PLAYER = {
    "playabilityStatus": {"status": "ERROR", "reason": "Video unavailable"},
    "videoDetails": {},
}


def test_status_field_ok_video():
    """A playable video reports status='ok' with no reason, and carries
    the status lifecycle timestamps."""
    fetcher = _video_fetcher_returning(_OK_PLAYER)
    m = fetcher.get_video_metadata("dQw4w9WgXcQ")
    assert m["status"] == "ok"
    assert m["status_reason"] is None
    assert m["status_checked_at"]  # ISO string set
    assert m["status_changed_at"] == m["status_checked_at"]  # first sighting


def test_status_field_unavailable_video_no_junk_dict():
    """A deleted/unavailable video reports status='unavailable' with
    YouTube's reason — instead of the old junk dict (title=None,
    view_count=0 with no signal)."""
    fetcher = _video_fetcher_returning(_DELETED_PLAYER)
    m = fetcher.get_video_metadata("dQw4w9WgXcQ")
    assert m["status"] == "unavailable"
    assert m["status_reason"] == "Video unavailable"


def test_status_preserves_last_known_good_on_becoming_unavailable(mocker):
    """When a previously-ok video becomes unavailable, the result keeps
    the last-known-good content fields and stamps status_changed_at at
    the moment of change."""
    times = iter(["2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"])
    mocker.patch("yt_meta.fetchers._utcnow_iso", side_effect=lambda: next(times))

    cache = {}
    ok_fetcher = _video_fetcher_returning(_OK_PLAYER)
    ok_fetcher.cache = cache
    first = ok_fetcher.get_video_metadata("dQw4w9WgXcQ")
    assert first["status"] == "ok"
    assert first["title"] == "Never Gonna Give You Up"

    gone_fetcher = _video_fetcher_returning(_DELETED_PLAYER)
    gone_fetcher.cache = cache
    second = gone_fetcher.get_video_metadata("dQw4w9WgXcQ", force_refresh=True)

    assert second["status"] == "unavailable"
    assert second["status_reason"] == "Video unavailable"
    # Last-known-good content preserved:
    assert second["title"] == "Never Gonna Give You Up"
    assert second["view_count"] == 1000
    # Change recorded at the second fetch's timestamp, not the first:
    assert second["status_changed_at"] == "2026-02-01T00:00:00+00:00"
    assert second["status_checked_at"] == "2026-02-01T00:00:00+00:00"


def test_status_changed_at_carried_forward_when_unchanged(mocker):
    """If status is unchanged across fetches, status_changed_at is
    carried forward (not bumped) while status_checked_at advances."""
    times = iter(["2026-01-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00"])
    mocker.patch("yt_meta.fetchers._utcnow_iso", side_effect=lambda: next(times))

    cache = {}
    f1 = _video_fetcher_returning(_OK_PLAYER)
    f1.cache = cache
    f1.get_video_metadata("dQw4w9WgXcQ")

    f2 = _video_fetcher_returning(_OK_PLAYER)
    f2.cache = cache
    m = f2.get_video_metadata("dQw4w9WgXcQ", force_refresh=True)

    assert m["status_changed_at"] == "2026-01-01T00:00:00+00:00"  # carried forward
    assert m["status_checked_at"] == "2026-03-01T00:00:00+00:00"  # advanced


_UPCOMING_PLAYER = {
    "playabilityStatus": {
        "status": "LIVE_STREAM_OFFLINE",
        "reason": "This live event will begin in 2 days.",
    },
    "videoDetails": {
        "videoId": "yl2jsIoMfDU",
        "title": "WWDC26: Platforms State of the Union | Apple",
        "author": "Apple",
        "isUpcoming": True,
        "isLiveContent": True,  # note: True for upcoming too
        "lengthSeconds": "0",
        "viewCount": "0",
    },
    "microformat": {
        "playerMicroformatRenderer": {
            "liveBroadcastDetails": {
                "isLiveNow": False,
                "startTimestamp": "2026-06-08T20:00:00+00:00",
            }
        }
    },
}


def test_status_upcoming_video():
    """An upcoming (scheduled) live event reports status='upcoming',
    is_upcoming=True, a scheduled_start_time, and is_live=False (it's not
    streaming yet)."""
    fetcher = _video_fetcher_returning(_UPCOMING_PLAYER)
    m = fetcher.get_video_metadata("yl2jsIoMfDU")
    assert m["status"] == "upcoming"
    assert m["status_reason"] == "This live event will begin in 2 days."
    assert m["is_upcoming"] is True
    assert m["is_live"] is False  # not live yet, despite isLiveContent=True
    assert m["scheduled_start_time"] == "2026-06-08T20:00:00+00:00"


def test_status_live_now_video():
    """A currently-live stream reports is_live=True (from
    liveBroadcastDetails.isLiveNow), status='ok', is_upcoming=False."""
    live_player = {
        "playabilityStatus": {"status": "OK"},
        "videoDetails": {
            "videoId": "dQw4w9WgXcQ",
            "title": "Live now",
            "isLiveContent": True,
            "lengthSeconds": "0",
            "viewCount": "10",
        },
        "microformat": {
            "playerMicroformatRenderer": {
                "liveBroadcastDetails": {"isLiveNow": True}
            }
        },
    }
    m = _video_fetcher_returning(live_player).get_video_metadata("dQw4w9WgXcQ")
    assert m["status"] == "ok"
    assert m["is_live"] is True
    assert m["is_upcoming"] is False
    assert m["scheduled_start_time"] is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/live/yl2jsIoMfDU?si=TxAEF7Q3t3",
        "https://www.youtube.com/live/yl2jsIoMfDU",
        "https://www.youtube.com/watch?v=yl2jsIoMfDU",
        "https://youtu.be/yl2jsIoMfDU",
        "https://www.youtube.com/shorts/yl2jsIoMfDU",
        "yl2jsIoMfDU",
    ],
)
def test_extract_video_id_handles_all_url_forms(url):
    """REGRESSION: /live/ URLs (with optional ?si= share param) — e.g. a
    link to a scheduled premiere — were not handled by extract_video_id.
    All supported forms resolve to the same canonical id."""
    from yt_meta.utils import extract_video_id

    assert extract_video_id(url) == "yl2jsIoMfDU"


def test_get_video_metadata_accepts_bare_id_builds_watch_url():
    """REGRESSION: get_video_metadata previously fetched the raw input as
    a URL, so a bare id raised RequestError. It now builds a canonical
    watch URL from the resolved id."""
    fetcher = _video_fetcher_returning(_OK_PLAYER)
    fetcher.get_video_metadata("dQw4w9WgXcQ")  # bare id — must not raise
    called_url = fetcher.session.get.call_args[0][0]
    assert called_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def mocked_video_fetcher():
    """Provides a VideoFetcher instance with a mocked session for unit tests."""
    with patch("httpx.Client") as mock_session:
        # We can further configure the mock session if needed per test
        yield VideoFetcher(session=mock_session, cache={})


def test_get_video_metadata_unavailable_raises_error(mocked_video_fetcher):
    """
    Tests that a 404 response from session.get raises our custom error.
    """
    mocked_video_fetcher.session.get.side_effect = VideoUnavailableError(
        "Video is private"
    )
    with pytest.raises(VideoUnavailableError, match="Video is private"):
        mocked_video_fetcher.get_video_metadata(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )


def test_m17_final_get_video_id_method_removed(mocked_video_fetcher):
    """REGRESSION (M17 final): VideoFetcher.get_video_id was deprecated
    in v0.4.0 (delegating to utils.extract_video_id with a
    DeprecationWarning) and is now removed in v0.6.0 as planned. The
    Facade always uses utils.extract_video_id directly (set up in
    v0.4.0); the only thing that needed to wait for v0.6.0 was actually
    deleting the method body. Test confirms the attribute is gone.
    """
    assert not hasattr(mocked_video_fetcher, "get_video_id"), (
        "VideoFetcher.get_video_id should be removed in v0.6.0 (deprecated "
        "in v0.4.0). Use yt_meta.utils.extract_video_id directly."
    )


def test_m13_extract_video_id_rejects_non_11_char_strings():
    """REGRESSION (M13): extract_video_id had a pass-through fallback
    that returned ANY non-http string unchanged — meaning "test_id",
    "../etc/passwd", "1; DROP TABLE", and similar were silently accepted
    as "video IDs". For a library whose extracted ID can flow into URLs
    and cache keys, that's a real risk: the cache key becomes
    `video_meta:../etc/passwd`, and downstream URL construction can
    embed user-controlled data.

    Tighten to require the canonical 11-character YouTube ID format
    (alphanumeric + `_` and `-`). Garbage raises ValueError.
    """
    from yt_meta.utils import extract_video_id

    for bad in ("test_id", "garbage", "../../etc/passwd", "abc", ""):
        with pytest.raises(ValueError, match="(Could not extract|Invalid)"):
            extract_video_id(bad)


def test_m13_extract_video_id_accepts_valid_11_char_id():
    """REGRESSION (M13): the strict check still accepts the canonical
    11-char form callers pass directly (e.g. from cached metadata).
    """
    from yt_meta.utils import extract_video_id

    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("jNQXAC9IVRw") == "jNQXAC9IVRw"


def test_m13_channel_fetcher_rejects_non_youtube_host():
    """REGRESSION (M13): ChannelFetcher.session.get used to fetch
    whatever channel_url the caller passed, with no host check. A
    `https://evil.example.com/@user/videos` URL would happily be fetched
    — a tidy SSRF primitive for any code path that takes channel URLs
    from user input (web forms, GETP params, queue payloads). Now
    rejected before any network call.
    """
    from unittest.mock import MagicMock

    from yt_meta.fetchers import ChannelFetcher, VideoFetcher

    session = MagicMock()
    session.get.side_effect = AssertionError("network must not be called")
    fetcher = ChannelFetcher(
        session=session, cache={}, video_fetcher=MagicMock(spec=VideoFetcher)
    )

    for bad in (
        "https://evil.example.com/@user/videos",
        "http://attacker.test/@user/videos",
        "https://youtubee.com/@user/videos",
        "file:///etc/passwd",
    ):
        with pytest.raises(ValueError, match="hostname"):
            fetcher._get_channel_page_data(bad)


def test_h6_video_metadata_cache_key_canonical_across_url_forms():
    """REGRESSION (H6): VideoFetcher.get_video_metadata built the cache
    key from `youtube_url.split("v=")[-1]`, so:
      - "https://www.youtube.com/watch?v=abc&t=42" → key "video_meta:abc&t=42"
      - "https://www.youtube.com/watch?v=abc"      → key "video_meta:abc"
      - "https://youtu.be/abc"                     → key "video_meta:https://youtu.be/abc"
    Same video, cached under up to four different keys; later calls
    with slightly different URLs missed cache and fetched again.

    Fix routes through utils.extract_video_id, the canonical 11-char id,
    so every URL form of the same video shares a single cache entry.
    """
    from unittest.mock import Mock

    from yt_meta.fetchers import VideoFetcher

    session = Mock()
    session.get.side_effect = AssertionError(
        "network should not be called — every URL form must hit the cache"
    )

    cached = {"title": "test", "video_id": "dQw4w9WgXcQ"}
    cache = {"video_meta:dQw4w9WgXcQ": cached}
    fetcher = VideoFetcher(session=session, cache=cache)

    for url in (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
    ):
        result = fetcher.get_video_metadata(url)
        assert result == cached, f"cache miss for url {url!r}"
