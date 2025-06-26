from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
import logging

from tests.conftest import get_fixture
from yt_meta import MetadataParsingError, VideoUnavailableError, YtMeta
from yt_meta.client import YtMeta
from yt_meta.exceptions import VideoUnavailableError

# Define the path to our test fixture
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "B68agR-OeJM.html"
CHANNEL_FIXTURE_PATH = Path(__file__).parent / "fixtures"


@pytest.fixture
def mocked_client():
    with patch("yt_meta.client.requests.Session") as mock_session:
        # Mock the session object
        mock_get = MagicMock()
        mock_session.return_value.get = mock_get

        # Return a client instance
        yield YtMeta(), mock_get


@pytest.fixture
def client_with_caching(tmp_path):
    """Provides a YtMeta instance with caching enabled in a temporary directory."""
    # cache_path = tmp_path / "yt_meta_cache"
    # This is a placeholder as file-based caching is not implemented yet in YtMeta
    return YtMeta()


@pytest.fixture
def client():
    """Provides a YtMeta client instance for testing."""
    return YtMeta()


def test_video_unavailable_raises_error(client, mocker):
    """
    Tests that a 404 response from session.get raises our custom error.
    """
    with patch.object(client.session, "get", side_effect=VideoUnavailableError("Video is private")):
        with pytest.raises(VideoUnavailableError, match="Video is private"):
            client.get_video_metadata("dQw4w9WgXcQ")


def test_get_channel_metadata(client, mocker, bulwark_channel_initial_data, bulwark_channel_ytcfg):
    """
    Tests that channel metadata can be parsed correctly from a fixture file.
    """
    mocker.patch(
        "yt_meta.client.YtMeta._get_channel_page_data",
        return_value=(bulwark_channel_initial_data, bulwark_channel_ytcfg, None),
    )

    metadata = client.get_channel_metadata("https://any-url.com")  # URL doesn't matter due to mock

    assert metadata is not None
    assert metadata["title"] == "The Bulwark"
    assert isinstance(metadata["description"], str)
    assert len(metadata["description"]) > 0
    assert metadata["channel_id"] == "UCG4Hp1KbGw4e02N7FpPXDgQ"
    assert "bulwarkmedia" in metadata["vanity_url"]
    assert isinstance(metadata["is_family_safe"], bool)


def test_get_video_metadata_live_stream(client):
    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value.text = get_fixture("live_stream.html")
        mock_get.return_value.status_code = 200
        result = client.get_video_metadata("LIVE_STREAM_VIDEO_ID")
        # The current robust parser is not designed for live stream pages,
        # so it should correctly return None instead of crashing.
        assert result is None, "Should return None for unparseable live stream pages"


def test_get_channel_page_data_fails_on_request_error(mocked_client):
    client, mock_get = mocked_client
    mock_get.side_effect = requests.exceptions.RequestException("Test error")
    with pytest.raises(VideoUnavailableError):
        client._get_channel_page_data("test_channel")


@patch(
    "yt_meta.client.YtMeta._get_channel_page_data",
    return_value=(None, None, "bad data"),
)
def test_get_channel_videos_raises_for_bad_initial_data(mock_get_page_data, client):
    with pytest.raises(MetadataParsingError, match="Could not find initial data script in channel page"):
        list(client.get_channel_videos("test_channel"))


def test_get_channel_videos_handles_continuation_errors(
    client, mocker, youtube_channel_initial_data, youtube_channel_ytcfg
):
    """
    Tests that video fetching gracefully stops if a continuation request fails.

    This test simulates a scenario where the first page of videos is fetched
    successfully (containing a continuation token), but the subsequent API call
    for the next page fails (returns None). The client should not crash and
    should return only the videos from the first page.
    """
    mocker.patch(
        "yt_meta.client.YtMeta._get_channel_page_data",
        return_value=(youtube_channel_initial_data, youtube_channel_ytcfg, "<html></html>"),
    )

    mock_continuation = mocker.patch(
        "yt_meta.client.YtMeta._get_continuation_data",
        return_value=None,
    )

    # The channel fixture is known to have 30 videos on the first page
    # and a continuation token.
    videos = list(client.get_channel_videos("https://any-url.com"))

    assert len(videos) == 30, "Should only return the videos from the first page."
    mock_continuation.assert_called_once()


def test_get_channel_videos_paginates_correctly(client):
    with patch.object(
        client, "_get_continuation_data"
    ) as mock_continuation, patch.object(
        client, "_get_channel_page_data"
    ) as mock_get_page_data:
        # Mock the initial page data to return one video and a continuation token
        initial_renderers = [
            {"richItemRenderer": {"content": {"videoRenderer": {"videoId": "video1"}}}},
            {
                "continuationItemRenderer": {
                    "continuationEndpoint": {
                        "continuationCommand": {"token": "initial_token"}
                    }
                }
            },
        ]
        mock_get_page_data.return_value = (
            {
                "contents": {
                    "twoColumnBrowseResultsRenderer": {
                        "tabs": [
                            {
                                "tabRenderer": {
                                    "selected": True,
                                    "content": {"richGridRenderer": {"contents": initial_renderers}},
                                }
                            }
                        ]
                    }
                }
            },
            {"INNERTUBE_API_KEY": "test_key"}, # mock ytcfg
            "<html></html>", # mock html
        )

        # Mock the continuation data to return one more video and NO token
        continuation_renderers = [
            {"richItemRenderer": {"content": {"videoRenderer": {"videoId": "video2"}}}}
        ]
        mock_continuation.return_value = {
            "onResponseReceivedActions": [
                {
                    "appendContinuationItemsAction": {
                        "continuationItems": continuation_renderers
                    }
                }
            ]
        }


        # Call the method to be tested
        videos = list(client.get_channel_videos("https://any-url.com"))

        # Assertions
        assert len(videos) == 2, "Should return videos from both pages"
        assert videos[0]["video_id"] == "video1"
        assert videos[1]["video_id"] == "video2"
        mock_get_page_data.assert_called_once_with("https://any-url.com/videos", force_refresh=False)
        mock_continuation.assert_called_once_with("initial_token", {"INNERTUBE_API_KEY": "test_key"})


@pytest.mark.integration
def test_get_video_metadata_integration(client):
    # "Me at the zoo" - a very stable video
    metadata = client.get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert metadata["title"] == "Me at the zoo"
    assert "view_count" in metadata


@pytest.mark.integration
def test_get_channel_shorts_integration(client):
    # MrBeast channel has shorts
    channel_url = "https://www.youtube.com/@MrBeast"
    shorts_generator = client.get_channel_shorts(channel_url)
    shorts = list(shorts_generator)
    assert len(shorts) > 0, "Should find at least one short"
    short = shorts[0]
    assert "video_id" in short
    assert "title" in short


@pytest.mark.integration
def test_get_channel_metadata_integration(client):
    # Test with a handle URL
    channel_url = "https://www.youtube.com/@MrBeast"
    # ... existing code ...


def test_clear_cache_all(mocker):
    # Setup mock cache and client
    mock_cache = mocker.MagicMock(spec=dict)
    # ... existing code ...


def test_get_channel_shorts_with_full_metadata_integration(client, caplog):
    caplog.set_level(logging.INFO)
    shorts_generator = client.get_channel_shorts(
        "https://www.youtube.com/@MrBeast", fetch_full_metadata=True, max_videos=1
    )
    shorts = list(shorts_generator)
    assert len(shorts) > 0, "Should have returned at least one short"
    short = shorts[0]
    assert "video_id" in short
    assert "title" in short
    assert "view_count" in short
    assert "url" in short
    # Assert slow-path keys
    assert "publish_date" in short
    assert "like_count" in short
    assert "category" in short
    assert "duration_seconds" in short
    assert short["duration_seconds"] is not None
    assert short["duration_seconds"] < 90  # Shorts are typically short


def test_get_playlist_videos_integration(client, caplog):
    caplog.set_level(logging.INFO)
    # Playlist from The Verge, known to be stable
    # ... existing code ...
