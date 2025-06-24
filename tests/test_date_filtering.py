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
    Tests filtering with a relative shorthand string for start_date.
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
    Tests that the end_date correctly filters out newer videos using a
    tighter, more recent window to speed up the test.
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
def test_stop_pagination_works_efficiently(client):
    """
    Tests the stop pagination logic efficiently by NOT fetching full metadata.
    This confirms the core stop logic without excessive network calls.
    """
    start_date = date.today() - timedelta(days=7)

    # fetch_full_metadata is False to make this test extremely fast
    videos_generator = client.get_channel_videos(LIVE_CHANNEL_URL, start_date="7d", fetch_full_metadata=False)
    videos = list(videos_generator)

    # This channel posts frequently, but likely not more than 30 times a week.
    # If this test returns > 50 videos, pagination likely isn't stopping correctly.
    assert len(videos) > 0 and len(videos) < 50, (
        "Returned an invalid number of videos, pagination might not be stopping correctly"
    )

    # Check that the last video is roughly within the date range
    last_video_published_text = videos[-1].get("publishedTimeText")
    if last_video_published_text:
        estimated_date = date.today() - timedelta(weeks=2)  # Give a 1 week buffer
        assert estimated_date <= start_date


@pytest.mark.integration
def test_playlist_filter_by_start_date_shorthand(client):
    """
    Tests filtering a playlist with a relative shorthand string for start_date.
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
    Tests that the end_date correctly filters out newer videos in a playlist.
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
def test_playlist_filter_efficiently(client):
    """
    Tests filtering a playlist efficiently by NOT fetching full metadata.
    This relies on the estimated date from `publishedTimeText`.
    """
    # Use a wide date range where videos are known to exist.
    # The test playlist has videos from ~8 years ago.
    start_date = "9y"
    end_date = "7y"

    # fetch_full_metadata is False to make this test extremely fast
    videos_generator = client.get_playlist_videos(
        LIVE_PLAYLIST_ID,
        start_date=start_date,
        end_date=end_date,
        fetch_full_metadata=False,
    )
    videos = list(videos_generator)

    assert len(videos) > 0, "Should find videos in the specified window"

    # Check that at least one video has a publishedTimeText
    assert any(
        v.get("publishedTimeText") for v in videos
    ), "At least one video should have a publishedTimeText"
