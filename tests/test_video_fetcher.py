from unittest.mock import patch

import pytest

from yt_meta import VideoUnavailableError, YtMeta
from yt_meta.fetchers import VideoFetcher


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


@pytest.mark.integration
def test_get_video_metadata_integration(video_fetcher: VideoFetcher):
    # "Me at the zoo" - a very stable video
    metadata = video_fetcher.get_video_metadata(
        "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    )
    assert metadata["title"] == "Me at the zoo"
    assert "view_count" in metadata


@pytest.mark.integration
def test_get_video_comments_integration(isolated_client: YtMeta):
    # Use a video with a stable, moderate number of comments.
    comments = isolated_client.comment_fetcher.get_comments("B68agR-OeJM", limit=10)
    comment_list = list(comments)
    assert len(comment_list) > 0
    assert "text" in comment_list[0]
    assert "author" in comment_list[0]
    assert "like_count" in comment_list[0]
