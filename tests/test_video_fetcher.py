import warnings
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


def test_regression_m17_get_video_id_handles_youtu_be_url(mocked_video_fetcher):
    """REGRESSION (M17): VideoFetcher.get_video_id reimplemented
    utils.extract_video_id worse — handled only `v=` and `/shorts/` patterns
    and raised ValueError on `youtu.be/` URLs. The Facade calls this method
    (client.py:254/286/317), so client.get_video_comments(
    'https://youtu.be/<id>') crashed on the most common short-form URL.

    Fix delegates to utils.extract_video_id, which already supports all four
    forms (`v=`, `/shorts/`, `youtu.be/`, bare 11-char id).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert (
            mocked_video_fetcher.get_video_id("https://youtu.be/dQw4w9WgXcQ")
            == "dQw4w9WgXcQ"
        )


def test_regression_m17_get_video_id_emits_deprecation_warning(mocked_video_fetcher):
    """REGRESSION (M17): VideoFetcher.get_video_id is deprecated in v0.4.0;
    callers should use yt_meta.utils.extract_video_id directly. Removal in
    v0.6.0 per the roadmap.
    """
    with pytest.warns(DeprecationWarning, match="extract_video_id"):
        mocked_video_fetcher.get_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )


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
