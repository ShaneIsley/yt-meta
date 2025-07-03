from unittest.mock import MagicMock, patch

from tests.conftest import make_mock_html
from yt_meta import YtMeta


def test_video_metadata_caching(tmp_path):
    """Verify that video metadata is cached and retrieved."""
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    mock_response = MagicMock()
    player_response = {
        "videoDetails": {"videoId": "dQw4w9WgXcQ"},
        "microformat": {"playerMicroformatRenderer": {}},
    }
    initial_data = {
        "contents": {},
        "frameworkUpdates": {"entityBatchUpdate": {"mutations": []}},
    }
    mock_response.text = make_mock_html(player_response, initial_data)
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_response) as mock_get:
        # First call - should fetch and cache
        client.get_video_metadata(video_url)
        mock_get.assert_called_once()

        # Second call - should hit the cache
        client.get_video_metadata(video_url)
        mock_get.assert_called_once()  # Should not be called again


def test_cache_persistence(tmp_path):
    """Verify that the cache persists across different YtMeta instances."""
    cache_file = tmp_path / "cache.db"
    client1 = YtMeta(cache_path=str(cache_file))
    key, value = "test_key", "test_value"
    client1.cache[key] = value
    del client1

    client2 = YtMeta(cache_path=str(cache_file))
    assert client2.cache[key] == value


def test_clear_cache(tmp_path):
    """Verify that the cache can be cleared."""
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    client.cache["key1"] = "value1"
    client.clear_cache()
    assert len(client.cache) == 0


def test_channel_page_caching(tmp_path):
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    channel_url = "https://www.youtube.com/channel/test/videos"

    # Create a proper mock response with ytcfg
    mock_response = MagicMock()
    mock_response.status_code = 200
    ytcfg = {"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {}}
    initial_data = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [{"tabRenderer": {"selected": True, "title": "Test Channel"}}],
                "header": {"c4TabbedHeaderRenderer": {"title": "Test Channel"}},
            }
        },
        "metadata": {
            "channelMetadataRenderer": {
                "title": "Test Channel",
                "description": "Test Description",
                "externalId": "UCtest123",
                "vanityChannelUrl": "https://www.youtube.com/@testchannel",
                "isFamilySafe": True,
            }
        },
    }
    html_content = make_mock_html(None, initial_data, ytcfg)
    mock_response.text = html_content
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_response) as mock_get:
        # First call should trigger a network request
        result1 = client.get_channel_metadata(channel_url)
        mock_get.assert_called_once()
        assert result1 is not None

        # Second call should hit the cache
        result2 = client.get_channel_metadata(channel_url)
        mock_get.assert_called_once()  # Should not be called again
        assert result2 == result1

        # Third call with force_refresh should trigger another request
        result3 = client.get_channel_metadata(channel_url, force_refresh=True)
        assert mock_get.call_count == 2
        assert result3 is not None
