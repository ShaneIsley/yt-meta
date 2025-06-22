import time

import pytest

from yt_meta import YtMetaClient

# A list of diverse YouTube channels for live testing
LIVE_CHANNEL_URLS = [
    "https://www.youtube.com/@samwitteveenai/videos",
    "https://www.youtube.com/@bulwarkmedia/videos",
    "https://www.youtube.com/@AI-Makerspace/videos",
]


@pytest.fixture
def client():
    """Provides a fresh instance of the client for each test, ensuring no state is shared."""
    return YtMetaClient()


@pytest.mark.integration
@pytest.mark.parametrize("channel_url", LIVE_CHANNEL_URLS)
def test_live_caching_is_faster(client, channel_url):
    """
    Tests that a cached call is significantly faster than the initial network call
    by fetching from a live channel.
    """
    # First call - makes a network request
    start_time_first = time.time()
    client.get_channel_metadata(channel_url)
    duration_first = time.time() - start_time_first

    # Second call - should hit the cache
    start_time_second = time.time()
    client.get_channel_metadata(channel_url)
    duration_second = time.time() - start_time_second

    print(f"\n[{channel_url}] First call: {duration_first:.4f}s, Cached call: {duration_second:.4f}s")
    # The cached call should be at least 100x faster (realistically more)
    assert duration_second < duration_first / 100


@pytest.mark.integration
@pytest.mark.parametrize("channel_url", LIVE_CHANNEL_URLS)
def test_live_force_refresh_bypasses_cache(client, channel_url):
    """
    Tests that `force_refresh=True` correctly re-fetches data by making two
    network calls of similar duration.
    """
    # Initial call to populate the cache
    start_time_initial = time.time()
    client.get_channel_metadata(channel_url)
    duration_initial = time.time() - start_time_initial

    # Second call with force_refresh should also make a network request
    start_time_refresh = time.time()
    client.get_channel_metadata(channel_url, force_refresh=True)
    duration_refresh = time.time() - start_time_refresh

    print(f"\n[{channel_url}] Initial call: {duration_initial:.4f}s, Refresh call: {duration_refresh:.4f}s")
    # Both calls should take a similar amount of time; we'll check if the refresh
    # call took at least 20% of the time of the initial call.
    assert duration_refresh > duration_initial * 0.2


def test_clear_cache_all(client, mocker):
    """Tests that clear_cache() without arguments clears the entire cache."""
    # Mock the internal cache to control its state
    client._channel_page_cache = {"url1": "data1", "url2": "data2"}

    # Act
    client.clear_cache()

    # Assert
    assert not client._channel_page_cache  # Cache should be empty


def test_clear_cache_specific_url(client, mocker):
    """Tests that clear_cache() with a URL clears only that entry."""
    # Arrange
    client._channel_page_cache = {
        "https://www.youtube.com/@channel1/videos": "data1",
        "https://www.youtube.com/@channel2/videos": "data2",
    }

    # Act
    client.clear_cache("https://www.youtube.com/@channel1/videos")

    # Assert
    assert "https://www.youtube.com/@channel1/videos" not in client._channel_page_cache
    assert "https://www.youtube.com/@channel2/videos" in client._channel_page_cache


def test_clear_cache_handles_trailing_slash(client, mocker):
    """
    Tests that clear_cache() correctly handles URLs with or without a trailing slash.
    """
    # Arrange
    url_with_slash = "https://www.youtube.com/@channel1/videos/"
    url_without_slash = "https://www.youtube.com/@channel1/videos"
    client._channel_page_cache = {url_without_slash: "data1"}

    # Act
    client.clear_cache(url_with_slash)

    # Assert
    assert not client._channel_page_cache
