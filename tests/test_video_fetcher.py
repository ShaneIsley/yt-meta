from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import Client

from yt_meta.fetchers import VideoFetcher
from yt_meta.exceptions import VideoUnavailableError


@pytest.fixture
def video_fetcher():
    """Provides a VideoFetcher instance with a mocked session."""
    with patch("httpx.Client") as mock_session:
        # We can further configure the mock session if needed per test
        yield VideoFetcher(session=mock_session, cache={})


def test_get_video_metadata_unavailable_raises_error(video_fetcher):
    """
    Tests that a 404 response from session.get raises our custom error.
    """
    video_fetcher.session.get.side_effect = VideoUnavailableError("Video is private")
    with pytest.raises(VideoUnavailableError, match="Video is private"):
        video_fetcher.get_video_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


@pytest.mark.integration
def test_get_video_metadata_integration():
    # We need a real client and session for an integration test
    fetcher = VideoFetcher(session=Client(), cache={})
    # "Me at the zoo" - a very stable video
    metadata = fetcher.get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert metadata["title"] == "Me at the zoo"
    assert "view_count" in metadata


@pytest.mark.integration
def test_get_video_comments_integration():
    # We need a real client and session for an integration test
    fetcher = VideoFetcher(session=Client(), cache={})
    # "Me at the zoo" - a very stable video
    comments = fetcher.get_video_comments("https://www.youtube.com/watch?v=jNQXAC9IVRw", limit=10)
    comment_list = list(comments)
    assert len(comment_list) > 0
    assert "text" in comment_list[0]
    assert "author" in comment_list[0]
    assert "like_count" in comment_list[0] 