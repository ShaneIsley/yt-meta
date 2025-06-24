import pytest
from yt_meta import YtMetaClient
from yt_meta.filtering import apply_filters, partition_filters
import logging

# --- Unit Tests for apply_filters ---

@pytest.fixture
def sample_video():
    """A sample video metadata object for testing filters."""
    return {
        "videoId": "test_id_123",
        "title": "A Great Video",
        "viewCount": 15000,
        # also testing the full metadata key
        "view_count": 15000,
        "lengthSeconds": 300,  # 5 minutes
        "duration_seconds": 300,
    }


def test_view_count_gt_passes(sample_video):
    filters = {"view_count": {"gt": 10000}}
    assert apply_filters(sample_video, filters) is True


def test_view_count_gt_fails(sample_video):
    filters = {"view_count": {"gt": 20000}}
    assert apply_filters(sample_video, filters) is False


def test_view_count_lt_passes(sample_video):
    filters = {"view_count": {"lt": 20000}}
    assert apply_filters(sample_video, filters) is True


def test_view_count_lt_fails(sample_video):
    filters = {"view_count": {"lt": 10000}}
    assert apply_filters(sample_video, filters) is False


def test_view_count_eq_passes(sample_video):
    filters = {"view_count": {"eq": 15000}}
    assert apply_filters(sample_video, filters) is True


def test_view_count_eq_fails(sample_video):
    filters = {"view_count": {"eq": 10000}}
    assert apply_filters(sample_video, filters) is False


def test_no_view_count_fails(sample_video):
    filters = {"view_count": {"gt": 10000}}
    del sample_video["viewCount"]
    del sample_video["view_count"]
    assert apply_filters(sample_video, filters) is False

# --- Unit Tests for duration_seconds ---

def test_duration_gt_passes(sample_video):
    filters = {"duration_seconds": {"gt": 60}}
    assert apply_filters(sample_video, filters) is True


def test_duration_lt_fails(sample_video):
    filters = {"duration_seconds": {"lt": 60}}
    assert apply_filters(sample_video, filters) is False


def test_duration_multiple_conditions_pass(sample_video):
    filters = {"duration_seconds": {"gte": 300, "lte": 300}}
    assert apply_filters(sample_video, filters) is True


def test_no_duration_fails(sample_video):
    filters = {"duration_seconds": {"gt": 100}}
    del sample_video["lengthSeconds"]
    del sample_video["duration_seconds"]
    assert apply_filters(sample_video, filters) is False

# --- Integration Test ---

@pytest.mark.integration
def test_live_view_count_filter(client: YtMetaClient):
    """
    Tests filtering a live channel by view count.
    This test is designed to be fast by fetching a small number of videos
    from a channel known to have videos with a wide range of view counts.
    """
    # Using a channel with a variety of view counts
    channel_url = "https://www.youtube.com/@TED/videos"
    filters = {"view_count": {"gt": 1_000_000}} # Videos with over 1 million views

    # We don't need full metadata since viewCount is in the basic renderer
    videos_generator = client.get_channel_videos(
        channel_url,
        filters=filters,
        fetch_full_metadata=False
    )

    count = 0
    for video in videos_generator:
        # Check first 5 videos that match
        if count >= 5:
            break
        assert video["viewCount"] > 1_000_000
        count += 1
    
    assert count > 0, "Should have found at least one video with over 1M views."


@pytest.mark.integration
def test_live_duration_filter_for_shorts(client: YtMetaClient):
    """
    Tests finding short videos (<= 60 seconds) from a channel.
    """
    # MrBeast is a good channel for this as he reliably posts Shorts
    channel_url = "https://www.youtube.com/@MrBeast/videos"
    filters = {"duration_seconds": {"lte": 60, "gt": 0}}

    # Duration is in basic metadata, so this is fast
    videos_generator = client.get_channel_videos(
        channel_url,
        filters=filters,
        fetch_full_metadata=False
    )

    count = 0
    for video in videos_generator:
        # Check first 5 videos that match
        if count >= 5:
            break
        assert video["lengthSeconds"] <= 60
        count += 1
    
    assert count > 0, "Should have found at least one YouTube Short."


def test_apply_filters_like_count():
    """Test filtering by like_count."""
    videos = [
        {"videoId": "1", "like_count": 50},
        {"videoId": "2", "like_count": 150},
        {"videoId": "3", "like_count": 100},
    ]
    filters = {"like_count": {"gte": 100}}
    filtered_videos = [v for v in videos if apply_filters(v, filters)]
    assert len(filtered_videos) == 2
    assert filtered_videos[0]["videoId"] == "2"
    assert filtered_videos[1]["videoId"] == "3"


def test_partition_filters():
    """Test the partitioning of filters into fast and slow."""
    filters = {
        "view_count": {"gt": 1000},
        "like_count": {"gte": 100},
        "duration_seconds": {"lt": 60},
        "unknown_filter": {"eq": True},
    }
    fast, slow = partition_filters(filters)
    assert "view_count" in fast
    assert "duration_seconds" in fast
    assert "like_count" in slow
    assert len(fast) == 2
    assert len(slow) == 1


def test_partition_filters_unrecognized_key_warning(caplog):
    """Test that an unrecognized filter key logs a warning."""
    filters = {
        "view_count": {"gt": 1000},
        "like_count": {"gte": 100},
        "duration_seconds": {"lt": 60},
        "unknown_filter": {"eq": True},
    }
    with caplog.at_level(logging.WARNING):
        fast, slow = partition_filters(filters)
        assert "view_count" in fast
        assert "duration_seconds" in fast
        assert "like_count" in slow
        assert len(fast) == 2
        assert len(slow) == 1
    assert "Unrecognized filter keys: {'unknown_filter'}" in caplog.text


def test_apply_filters_missing_key():
    """Test that apply_filters returns False if the video is missing a key."""
    video_missing_likes = {"videoId": "1", "viewCount": 100}
    filters = {"like_count": {"gt": 10}}
    assert not apply_filters(video_missing_likes, filters)


def test_apply_filters_description_snippet():
    """Tests filtering by description snippet."""
    videos = [
        {"descriptionSnippet": "A video about Python programming."},
        {"descriptionSnippet": "A great video about cooking."},
        {"descriptionSnippet": "A tutorial on pyTEst and other tools."},
    ]
    
    # Test 'contains'
    filters_py = {"description_snippet": {"contains": "python"}}
    filtered_py = [v for v in videos if apply_filters(v, filters_py)]
    assert len(filtered_py) == 1
    assert filtered_py[0]["descriptionSnippet"] == "A video about Python programming."

    # Test 're'
    filters_re = {"description_snippet": {"re": r"pyt(hon|est)"}}
    filtered_re = [v for v in videos if apply_filters(v, filters_re)]
    assert len(filtered_re) == 2


def test_apply_filters_title():
    """Tests filtering by video title."""
    videos = [
        {"title": "An Introduction to Python"},
        {"title": "Advanced Python Programming"},
        {"title": "A video about Rust"},
    ]

    # Test 'contains'
    filters_py = {"title": {"contains": "python"}}
    filtered_py = [v for v in videos if apply_filters(v, filters_py)]
    assert len(filtered_py) == 2

    # Test 're'
    filters_re = {"title": {"re": r"^Advanced"}}
    filtered_re = [v for v in videos if apply_filters(v, filters_re)]
    assert len(filtered_re) == 1
    assert filtered_re[0]["title"] == "Advanced Python Programming"


# --- Integration Tests ---


@pytest.mark.integration
def test_filter_by_view_count_integration(client):
    # a duration of 60 seconds or less.
    channel_url = "https://www.youtube.com/@TED/videos"
    filters = {"duration_seconds": {"lte": 60}}
    shorts = list(client.get_channel_videos(channel_url, filters=filters, fetch_full_metadata=False))
    count = len(shorts)

    # We expect to find at least one "short" video on the TED channel.
    assert count > 0, "Should have found at least one YouTube Short."
    assert all(video.get("lengthSeconds", 0) <= 60 for video in shorts)


@pytest.mark.integration
def test_combined_fast_and_slow_filters_integration(client):
    """
    Test a combination of fast (view_count) and slow (like_count) filters.
    This validates the two-stage filtering process.
    """
    # Use a specific, popular video that is likely to have consistent stats.
    # "Me at the zoo" - first video on YouTube.
    # It has >300M views and >14M likes.
    channel_url = "https://www.youtube.com/@jawed/videos"
    filters = {
        "view_count": {"gt": 100_000_000},  # Fast filter
        "like_count": {"gt": 10_000_000},  # Slow filter
    }
    videos = list(client.get_channel_videos(channel_url, filters=filters))

    # Expecting to find "Me at the zoo"
    assert len(videos) >= 1
    found_video = False
    for video in videos:
        if video["video_id"] == "jNQXAC9IVRw":
            assert video["view_count"] > 100_000_000
            assert video["like_count"] > 10_000_000
            found_video = True
            break
    assert found_video, "Did not find 'Me at the zoo' with combined filters." 