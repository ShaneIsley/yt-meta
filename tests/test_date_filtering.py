# tests/test_date_filtering.py
import itertools
from datetime import date, datetime, timedelta

import pytest

from yt_meta import YtMetaClient

# Using a channel with frequent uploads for reliable date testing
LIVE_CHANNEL_URL = "https://www.youtube.com/@samwitteveenai/videos"
# A playlist from the same channel with a good number of videos
LIVE_PLAYLIST_ID = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"
# How many videos to check in each test. Keep this low for speed.
VIDEO_SAMPLE_SIZE = 3


@pytest.mark.integration
def test_filter_by_start_date_shorthand(client):
    """
    Tests filtering videos using a shorthand start date (e.g., '1y').
    Uses a smaller date range to keep the test fast.
    """
    start_date = date.today() - timedelta(days=30)

    videos_generator = client.get_channel_videos(LIVE_CHANNEL_URL, start_date="30d", fetch_full_metadata=True)
    videos = list(itertools.islice(videos_generator, VIDEO_SAMPLE_SIZE))

    assert len(videos) > 0, "Should have found at least one video in the last 30 days"

    for video in videos:
        assert "publish_date" in video, "Full metadata should include publish_date"
        publish_date = datetime.fromisoformat(video["publish_date"]).date()
        assert publish_date >= start_date


@pytest.mark.integration
def test_filter_with_end_date(client):
    """
    Tests that filtering with an end_date correctly excludes newer videos.
    Uses a tighter, more recent window to speed up the test.
    """
    # A window from 40 to 20 days ago
    start_date = date.today() - timedelta(days=40)
    end_date = date.today() - timedelta(days=20)

    videos_generator = client.get_channel_videos(
        LIVE_CHANNEL_URL,
        start_date=start_date,
        end_date=end_date,
        fetch_full_metadata=True,
    )
    videos = list(itertools.islice(videos_generator, VIDEO_SAMPLE_SIZE))

    assert len(videos) > 0, "Should find videos in the specified window from the past"

    for video in videos:
        publish_date = datetime.fromisoformat(video["publish_date"]).date()
        assert start_date <= publish_date <= end_date, (
            f"Video with date {publish_date} is outside the expected range {start_date} to {end_date}"
        )


@pytest.mark.integration
def test_filter_with_start_and_end_date(client):
    """
    Tests that filtering with both start and end dates correctly includes
    videos within the specified date range.
    """
    # A window from 40 to 20 days ago
    start_date = date.today() - timedelta(days=40)
    end_date = date.today() - timedelta(days=20)

    videos_generator = client.get_channel_videos(
        LIVE_CHANNEL_URL,
        start_date=start_date,
        end_date=end_date,
        fetch_full_metadata=True,
    )
    videos = list(itertools.islice(videos_generator, VIDEO_SAMPLE_SIZE))

    assert len(videos) > 0, "Should find videos in the specified window from the past"

    for video in videos:
        publish_date = datetime.fromisoformat(video["publish_date"]).date()
        assert start_date <= publish_date <= end_date, (
            f"Video with date {publish_date} is outside the expected range {start_date} to {end_date}"
        )


@pytest.mark.integration
def test_playlist_filter_by_start_date_shorthand(client):
    """
    Tests filtering playlist videos using a shorthand start date (e.g., '3y').
    """
    start_date = date.today() - timedelta(days=90)  # A wider range for playlists

    videos_generator = client.get_playlist_videos(LIVE_PLAYLIST_ID, start_date="90d", fetch_full_metadata=True)
    videos = list(itertools.islice(videos_generator, VIDEO_SAMPLE_SIZE))

    assert len(videos) > 0, "Should have found at least one video in the last 90 days"

    for video in videos:
        assert "publish_date" in video, "Full metadata should include publish_date"
        publish_date = datetime.fromisoformat(video["publish_date"]).date()
        assert publish_date >= start_date


@pytest.mark.integration
def test_playlist_filter_with_end_date(client):
    """
    Tests that filtering a playlist with an end_date correctly excludes
    newer videos.
    """
    # A window from 180 to 90 days ago
    start_date = date.today() - timedelta(days=180)
    end_date = date.today() - timedelta(days=90)

    videos_generator = client.get_playlist_videos(
        LIVE_PLAYLIST_ID,
        start_date=start_date,
        end_date=end_date,
        fetch_full_metadata=True,
    )
    videos = list(itertools.islice(videos_generator, VIDEO_SAMPLE_SIZE))

    assert len(videos) > 0, "Should find videos in the specified window from the past"

    for video in videos:
        publish_date = datetime.fromisoformat(video["publish_date"]).date()
        assert start_date <= publish_date <= end_date, (
            f"Video with date {publish_date} is outside the expected range {start_date} to {end_date}"
        )


@pytest.mark.integration
def test_playlist_filter_with_start_and_end_date(client):
    """
    Tests that filtering a playlist with both start and end dates correctly
    includes videos within the specified date range.
    """
    # A window from 180 to 90 days ago
    start_date = date.today() - timedelta(days=180)
    end_date = date.today() - timedelta(days=90)

    videos_generator = client.get_playlist_videos(
        LIVE_PLAYLIST_ID,
        start_date=start_date,
        end_date=end_date,
        fetch_full_metadata=True,
    )
    videos = list(itertools.islice(videos_generator, VIDEO_SAMPLE_SIZE))

    assert len(videos) > 0, "Should find videos in the specified window from the past"

    for video in videos:
        publish_date = datetime.fromisoformat(video["publish_date"]).date()
        assert start_date <= publish_date <= end_date, (
            f"Video with date {publish_date} is outside the expected range {start_date} to {end_date}"
        )
