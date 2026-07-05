"""HTTP resilience at every GET site (C2 + C3, 2026-07-05 review).

Rule R1: these tests go through ``httpx.MockTransport`` returning REAL
status codes, so ``raise_for_status()`` raises the real
``httpx.HTTPStatusError`` — the exception class the buggy code's
``except httpx.RequestError`` silently missed. No hand-raised
exceptions, no private-method patching.

State space (R4): each GET site is exercised in two states — a
non-retryable client error (404) and a retryable transient (429 → 200).
"""

import httpx
import pytest

from tests.conftest import make_mock_html
from yt_meta.comment_api_client import CommentAPIClient
from yt_meta.exceptions import VideoUnavailableError
from yt_meta.fetchers import ChannelFetcher, PlaylistFetcher, VideoFetcher

_OK_PLAYER = {
    "playabilityStatus": {"status": "OK"},
    "videoDetails": {
        "videoId": "dQw4w9WgXcQ",
        "title": "T",
        "author": "A",
        "lengthSeconds": "212",
        "viewCount": "1000",
    },
    "microformat": {"playerMicroformatRenderer": {"publishDate": "2009-10-25"}},
}
_CHANNEL_DATA = {
    "metadata": {
        "channelMetadataRenderer": {
            "title": "C",
            "description": "d",
            "externalId": "UCxxxxxxxxxxxxxxxxxxxx",
            "isFamilySafe": True,
        }
    }
}


class _ScriptedTransport:
    """A MockTransport handler that plays a scripted list of responses
    and counts requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.request_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.request_count += 1
        status, text = self.responses.pop(0) if self.responses else (200, "")
        return httpx.Response(status, text=text)


def _session(transport: _ScriptedTransport) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(transport))


@pytest.fixture(autouse=True)
def _instant_retries(monkeypatch):
    """Make retry backoff instant so 429→200 tests don't sleep."""
    monkeypatch.setattr("yt_meta._retry.time.sleep", lambda _s: None)


# --- C2: 404 must surface as VideoUnavailableError, not HTTPStatusError ---


def test_c2_video_metadata_404_raises_video_unavailable():
    """REGRESSION (C2): a 404 on the watch page escaped the
    ``except httpx.RequestError`` guard as a raw HTTPStatusError,
    despite the docstring promising VideoUnavailableError for 404."""
    transport = _ScriptedTransport([(404, "")])
    with _session(transport) as session:
        fetcher = VideoFetcher(session=session, cache={})
        with pytest.raises(VideoUnavailableError):
            fetcher.get_video_metadata("dQw4w9WgXcQ")


def test_c2_channel_metadata_404_raises_video_unavailable():
    """REGRESSION (C2): same class of bug on the channel page GET."""
    transport = _ScriptedTransport([(404, "")])
    with _session(transport) as session:
        fetcher = ChannelFetcher(
            session=session, cache={}, video_fetcher=VideoFetcher(session, {})
        )
        with pytest.raises(VideoUnavailableError):
            fetcher.get_channel_metadata("https://www.youtube.com/@x")


def test_c2_playlist_404_raises_video_unavailable():
    """REGRESSION (C2): same class of bug on the playlist page GET."""
    transport = _ScriptedTransport([(404, "")])
    with _session(transport) as session:
        fetcher = PlaylistFetcher(
            session=session, cache={}, video_fetcher=VideoFetcher(session, {})
        )
        with pytest.raises(VideoUnavailableError):
            list(fetcher.get_playlist_videos("PLxxxx"))


@pytest.mark.parametrize("method", ["get_channel_videos", "get_channel_shorts", "get_channel_streams"])
def test_c2_channel_tab_404_yields_empty_not_crash(method):
    """REGRESSION (C2): the channel tab generators document "initial page
    fetch failure → logged, empty result" (they catch
    VideoUnavailableError from the page fetch). A 404 bypassed that
    contract and crashed the generator with HTTPStatusError."""
    transport = _ScriptedTransport([(404, "")])
    with _session(transport) as session:
        fetcher = ChannelFetcher(
            session=session, cache={}, video_fetcher=VideoFetcher(session, {})
        )
        assert list(getattr(fetcher, method)("https://www.youtube.com/@x")) == []


# --- C3: transient 429 must be retried at every GET site ---


def test_c3_video_metadata_retries_429_then_succeeds():
    """REGRESSION (C3): the watch-page GET — one per video during
    fetch_full_metadata=True hydration, the library's highest-volume
    request — had no retry. A single transient 429 aborted it."""
    html = make_mock_html(_OK_PLAYER, {"contents": {}})
    transport = _ScriptedTransport([(429, ""), (200, html)])
    with _session(transport) as session:
        fetcher = VideoFetcher(session=session, cache={})
        meta = fetcher.get_video_metadata("dQw4w9WgXcQ")
    assert meta is not None
    assert meta["title"] == "T"
    assert transport.request_count == 2


def test_c3_channel_page_retries_429_then_succeeds():
    """REGRESSION (C3): channel page GET had no retry."""
    html = make_mock_html(None, _CHANNEL_DATA)
    transport = _ScriptedTransport([(429, ""), (200, html)])
    with _session(transport) as session:
        fetcher = ChannelFetcher(
            session=session, cache={}, video_fetcher=VideoFetcher(session, {})
        )
        meta = fetcher.get_channel_metadata("https://www.youtube.com/@x")
    assert meta["title"] == "C"
    assert transport.request_count == 2


def test_c3_comment_initial_page_retries_429_then_succeeds():
    """REGRESSION (C3): the comment subsystem's initial watch-page GET
    had no retry (only its continuation POSTs did)."""
    html = make_mock_html(None, {"contents": {}})
    transport = _ScriptedTransport([(429, ""), (200, html)])
    with _session(transport) as session:
        client = CommentAPIClient(session=session)
        initial_data, ytcfg = client.get_initial_video_data("dQw4w9WgXcQ")
    assert initial_data == {"contents": {}}
    assert transport.request_count == 2
