from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from tests.conftest import get_fixture
from yt_meta import MetadataParsingError, VideoUnavailableError, YtMetaClient

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
        yield YtMetaClient(), mock_get


@pytest.fixture
def client_with_caching(tmp_path):
    """Provides a YtMetaClient instance with caching enabled in a temporary directory."""
    # cache_path = tmp_path / "yt_meta_cache"
    # This is a placeholder as file-based caching is not implemented yet in YtMetaClient
    return YtMetaClient()


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
        "yt_meta.client.YtMetaClient._get_channel_page_data",
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
        assert result["is_live"] is True, "Should correctly identify a live stream"


def test_get_channel_page_data_fails_on_request_error(mocked_client):
    client, mock_get = mocked_client
    mock_get.side_effect = requests.exceptions.RequestException("Test error")
    with pytest.raises(VideoUnavailableError):
        client._get_channel_page_data("test_channel")


@patch(
    "yt_meta.client.YtMetaClient._get_channel_page_data",
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
        "yt_meta.client.YtMetaClient._get_channel_page_data",
        return_value=(youtube_channel_initial_data, youtube_channel_ytcfg, "<html></html>"),
    )

    mock_continuation = mocker.patch(
        "yt_meta.client.YtMetaClient._get_continuation_data",
        return_value=None,
    )

    # The channel fixture is known to have 30 videos on the first page
    # and a continuation token.
    videos = list(client.get_channel_videos("https://any-url.com"))

    assert len(videos) == 30, "Should only return the videos from the first page."
    mock_continuation.assert_called_once()
