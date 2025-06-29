import pytest
from httpx import Client

from yt_meta.fetchers import PlaylistFetcher, VideoFetcher


@pytest.fixture
def video_fetcher():
    """Provides a real VideoFetcher instance for integration tests."""
    return VideoFetcher(session=Client(), cache={})


@pytest.fixture
def playlist_fetcher(video_fetcher):
    """Provides a PlaylistFetcher instance with a real session and video_fetcher."""
    return PlaylistFetcher(session=Client(), cache={}, video_fetcher=video_fetcher)


@pytest.mark.integration
def test_get_playlist_videos_integration(playlist_fetcher):
    # Google "110-language Google Translate journey 2024"
    playlist_id = "PLXFtMv-aATMXRyFmX7hw2D2j2LtmFW5un"
    videos = list(playlist_fetcher.get_playlist_videos(playlist_id, max_videos=3))
    assert len(videos) == 3
    assert "video_id" in videos[0]
    assert "title" in videos[0] 