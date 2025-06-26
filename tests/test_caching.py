import pytest
from diskcache import Cache
from unittest.mock import patch, MagicMock
import json

from yt_meta import YtMeta


def make_mock_html(player_response, initial_data):
    """Creates a minimal HTML structure for mocking video pages."""
    return f"""
    <html><body>
    <script>var ytInitialPlayerResponse = {json.dumps(player_response)};</script>
    <script>var ytInitialData = {json.dumps(initial_data)};</script>
    </body></html>
    """


@pytest.fixture
def temp_cache(tmp_path):
    """Provides a diskcache.Cache instance in a temporary directory."""
    cache_dir = tmp_path / "cache"
    cache = Cache(cache_dir)
    yield cache
    cache.close()


@pytest.fixture
def cached_client(temp_cache):
    """Provides a YtMeta instance with a temporary disk cache."""
    client = YtMeta(cache=temp_cache)
    return client


def test_video_metadata_caching(cached_client):
    """
    Tests that get_video_metadata caches its results.
    """
    video_url = "https://www.youtube.com/watch?v=test_video_id"

    # Mock the response from session.get
    mock_response = MagicMock()
    player_response = {"videoDetails": {}, "microformat": {"playerMicroformatRenderer": {}}}
    initial_data = {"contents": {}, "frameworkUpdates": {"entityBatchUpdate": {"mutations": []}}}
    mock_response.text = make_mock_html(player_response, initial_data)
    mock_response.raise_for_status = MagicMock()

    with patch("yt_meta.client.requests.Session.get", return_value=mock_response) as mock_get, \
         patch("yt_meta.client.parsing.parse_video_metadata", return_value={"meta": "data"}) as mock_parse:

        # First call - should fetch and cache
        result1 = cached_client.get_video_metadata(video_url)
        mock_get.assert_called_once()
        mock_parse.assert_called_once()
        assert result1 == {"meta": "data"}

        # Second call - should hit the cache
        result2 = cached_client.get_video_metadata(video_url)
        mock_get.assert_called_once()  # Should not be called again
        # The whole function is cached, so parsing shouldn't happen again either
        mock_parse.assert_called_once()
        assert result2 == result1


def test_cache_persistence(tmp_path):
    """
    Tests that the cache persists between YtMeta instances.
    """
    cache_dir = tmp_path / "cache"
    video_url = "https://www.youtube.com/watch?v=test_video_id_persistence"

    mock_response = MagicMock()
    player_response = {"videoDetails": {}, "microformat": {"playerMicroformatRenderer": {}}}
    initial_data = {"contents": {}, "frameworkUpdates": {"entityBatchUpdate": {"mutations": []}}}
    mock_response.text = make_mock_html(player_response, initial_data)
    mock_response.raise_for_status = MagicMock()

    with patch("yt_meta.client.requests.Session.get", return_value=mock_response), \
         patch("yt_meta.client.parsing.parse_video_metadata", return_value={"persistent": "data"}):

        # First client instance
        cache1 = Cache(cache_dir)
        client1 = YtMeta(cache=cache1)
        client1.get_video_metadata(video_url)
        cache1.close()

    # Second client instance with the same cache directory
    with patch("yt_meta.client.requests.Session.get", return_value=mock_response) as mock_get, \
         patch("yt_meta.client.parsing.parse_video_metadata") as mock_parse:
        cache2 = Cache(cache_dir)
        client2 = YtMeta(cache=cache2)
        result = client2.get_video_metadata(video_url)
        cache2.close()

        mock_get.assert_not_called()
        mock_parse.assert_not_called()
        assert result == {"persistent": "data"}


def test_continuation_caching(cached_client):
    """
    Tests that _get_continuation_data caches its results.
    """
    token = "test_token"
    ytcfg = {"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {}}
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": "continuation_data"}
    mock_response.raise_for_status = MagicMock()

    with patch("yt_meta.client.requests.Session.post", return_value=mock_response) as mock_post:
        # First call
        result1 = cached_client._get_continuation_data(token, ytcfg)
        mock_post.assert_called_once()
        assert result1 == {"data": "continuation_data"}

        # Second call
        result2 = cached_client._get_continuation_data(token, ytcfg)
        mock_post.assert_called_once()  # Should not be called again
        assert result2 == result1


def test_clear_cache(cached_client):
    """
    Tests that clear_cache clears the underlying cache.
    """
    video_url = "https://www.youtube.com/watch?v=another_video"
    mock_response = MagicMock()
    mock_response.text = '{"key": "value"}'
    mock_response.raise_for_status = MagicMock()

    with patch("yt_meta.client.requests.Session.get", return_value=mock_response) as mock_get, \
         patch("yt_meta.client.parsing.parse_video_metadata", return_value={"meta": "data"}):

        # Populate the cache
        cached_client.get_video_metadata(video_url)
        assert mock_get.call_count == 1

        # Clear the cache
        cached_client.clear_cache()

        # Fetch again
        cached_client.get_video_metadata(video_url)
        assert mock_get.call_count == 2  # Should be called again
