from unittest.mock import patch, MagicMock
import pytest
import requests
from httpx import Client

from yt_meta.fetchers import ChannelFetcher, VideoFetcher
from yt_meta.exceptions import MetadataParsingError, VideoUnavailableError


@pytest.fixture
def channel_fetcher():
    """Provides a ChannelFetcher instance with a mocked session and video_fetcher."""
    with patch("httpx.Client") as mock_session:
        mock_video_fetcher = MagicMock(spec=VideoFetcher)
        yield ChannelFetcher(session=mock_session, cache={}, video_fetcher=mock_video_fetcher)


@pytest.fixture
def fetcher(video_fetcher):
    """Provides a ChannelFetcher instance for integration tests."""
    return ChannelFetcher(session=Client(), cache={}, video_fetcher=video_fetcher)


@pytest.fixture
def video_fetcher():
    """Provides a real VideoFetcher instance for integration tests."""
    return VideoFetcher(session=Client(), cache={})


def test_get_channel_metadata(channel_fetcher, mocker, bulwark_channel_initial_data, bulwark_channel_ytcfg):
    mocker.patch.object(channel_fetcher, "_get_channel_page_data", return_value=(bulwark_channel_initial_data, bulwark_channel_ytcfg, None))
    metadata = channel_fetcher.get_channel_metadata("https://any-url.com")
    assert metadata is not None
    assert metadata["title"] == "The Bulwark"


def test_get_channel_page_data_fails_on_request_error(channel_fetcher):
    channel_fetcher.session.get.side_effect = requests.exceptions.RequestException("Test error")
    with pytest.raises(VideoUnavailableError):
        channel_fetcher._get_channel_page_data("test_channel")


@patch("yt_meta.fetchers.ChannelFetcher._get_channel_page_data", return_value=(None, None, "bad data"))
def test_get_channel_videos_raises_for_bad_initial_data(mock_get_page_data, channel_fetcher):
    with pytest.raises(MetadataParsingError, match="Could not find initial data script in channel page"):
        list(channel_fetcher.get_channel_videos("test_channel"))


def test_get_channel_videos_handles_continuation_errors(
    channel_fetcher, mocker, youtube_channel_initial_data, youtube_channel_ytcfg
):
    mocker.patch.object(channel_fetcher, "_get_channel_page_data", return_value=(youtube_channel_initial_data, youtube_channel_ytcfg, "<html></html>"))
    mocker.patch.object(channel_fetcher, "_get_continuation_data", return_value=None)
    videos = list(channel_fetcher.get_channel_videos("https://any-url.com"))
    assert len(videos) == 30


def test_get_channel_videos_paginates_correctly(channel_fetcher, mocker):
    with patch.object(channel_fetcher, "_get_continuation_data") as mock_continuation, \
         patch.object(channel_fetcher, "_get_channel_page_data") as mock_get_page_data:
        initial_renderers = [
            {"richItemRenderer": {"content": {"videoRenderer": {"videoId": "video1"}}}},
            {"continuationItemRenderer": {"continuationEndpoint": {"continuationCommand": {"token": "initial_token"}}}}
        ]
        mock_get_page_data.return_value = ({"contents": {"twoColumnBrowseResultsRenderer": {"tabs": [{"tabRenderer": {"selected": True, "content": {"richGridRenderer": {"contents": initial_renderers}}}}]}}}, {"INNERTUBE_API_KEY": "test_key"}, "<html></html>")
        continuation_renderers = [{"richItemRenderer": {"content": {"videoRenderer": {"videoId": "video2"}}}}]
        mock_continuation.return_value = {"onResponseReceivedActions": [{"appendContinuationItemsAction": {"continuationItems": continuation_renderers}}]}
        videos = list(channel_fetcher.get_channel_videos("https://any-url.com"))
        assert len(videos) == 2


@pytest.mark.integration
def test_get_channel_shorts_integration(fetcher):
    """Verify that get_channel_shorts fetches shorts data for a channel."""
    shorts = list(fetcher.get_channel_shorts("https://www.youtube.com/@bashbunni"))
    assert len(shorts) > 0
    assert "video_id" in shorts[0]


@pytest.mark.integration
def test_get_channel_metadata_integration(fetcher):
    """Verify that get_channel_metadata fetches the correct channel title."""
    metadata = fetcher.get_channel_metadata("https://www.youtube.com/@bashbunni")
    assert metadata["title"] == "bashbunni"


@pytest.mark.integration
def test_get_channel_videos_full_metadata_integration(fetcher):
    """Verify that full metadata fetching includes 'like_count'."""
    videos = list(fetcher.get_channel_videos(
        "https://www.youtube.com/@bashbunni", fetch_full_metadata=True, max_videos=1
    ))
    assert "like_count" in videos[0]


@pytest.mark.integration
def test_get_channel_shorts_with_full_metadata_integration(fetcher):
    shorts_generator = fetcher.get_channel_shorts(
        "https://www.youtube.com/@bashbunni", fetch_full_metadata=True, max_videos=1
    )
    shorts = list(shorts_generator)
    assert len(shorts) > 0
    short = shorts[0]
    assert "view_count" in short
    assert "publish_date" in short 