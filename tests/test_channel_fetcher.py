from unittest.mock import MagicMock, patch

import pytest

from yt_meta import YtMeta
from yt_meta.exceptions import MetadataParsingError
from yt_meta.fetchers import ChannelFetcher, VideoFetcher


@pytest.fixture
def channel_fetcher():
    """Provides a ChannelFetcher instance with a mocked session and video_fetcher."""
    with patch("httpx.Client") as mock_session:
        mock_video_fetcher = MagicMock(spec=VideoFetcher)
        yield ChannelFetcher(
            session=mock_session, cache={}, video_fetcher=mock_video_fetcher
        )


def test_get_channel_metadata_unit(
    channel_fetcher, mocker, bulwark_channel_initial_data, bulwark_channel_ytcfg
):
    mocker.patch.object(
        channel_fetcher,
        "_get_channel_page_data",
        return_value=(bulwark_channel_initial_data, bulwark_channel_ytcfg, None),
    )
    metadata = channel_fetcher.get_channel_metadata("https://any-url.com")
    assert metadata is not None
    assert metadata["title"] == "The Bulwark"


@patch(
    "yt_meta.fetchers.ChannelFetcher._get_channel_page_data",
    return_value=(None, None, "bad data"),
)
def test_get_channel_videos_raises_for_bad_initial_data(
    mock_get_page_data, channel_fetcher
):
    with pytest.raises(
        MetadataParsingError, match="Could not find initial data script in channel page"
    ):
        list(channel_fetcher.get_channel_videos("test_channel"))


def test_get_channel_videos_handles_continuation_errors(
    channel_fetcher, mocker, youtube_channel_initial_data, youtube_channel_ytcfg
):
    mocker.patch.object(
        channel_fetcher,
        "_get_channel_page_data",
        return_value=(
            youtube_channel_initial_data,
            youtube_channel_ytcfg,
            "<html></html>",
        ),
    )
    mocker.patch.object(channel_fetcher, "_get_continuation_data", return_value=None)
    videos = list(channel_fetcher.get_channel_videos("https://any-url.com"))
    assert len(videos) == 30


def test_get_channel_videos_paginates_correctly(channel_fetcher, mocker):
    with (
        patch.object(channel_fetcher, "_get_continuation_data") as mock_continuation,
        patch.object(channel_fetcher, "_get_channel_page_data") as mock_get_page_data,
    ):
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
                                    "content": {
                                        "richGridRenderer": {
                                            "contents": initial_renderers
                                        }
                                    },
                                }
                            }
                        ]
                    }
                }
            },
            {"INNERTUBE_API_KEY": "test_key"},
            "<html></html>",
        )
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
        videos = list(channel_fetcher.get_channel_videos("https://any-url.com"))
        assert len(videos) == 2


@pytest.mark.integration
def test_get_channel_videos_full_metadata_integration(isolated_client: YtMeta):
    """
    Tests that fetch_full_metadata correctly retrieves detailed metadata
    like 'like_count' for channel videos.
    """
    channel_url = "https://www.youtube.com/@TED/videos"
    videos_gen = isolated_client.get_channel_videos(
        channel_url, max_videos=3, fetch_full_metadata=True
    )
    videos = list(videos_gen)
    assert len(videos) > 0
    assert "like_count" in videos[0]
    assert isinstance(videos[0]["like_count"], int)


@pytest.mark.integration
def test_get_channel_metadata(isolated_client: YtMeta):
    """
    Tests fetching basic metadata for a real channel to ensure the parsing logic
    is robust against live data.
    """
    channel_url = "https://www.youtube.com/@TED"
    metadata = isolated_client.get_channel_metadata(channel_url)
    assert metadata["title"] == "TED"
    assert metadata["channel_id"] == "UCAuUUnT6oDeKwE6v1NGQxug"


@pytest.mark.integration
def test_get_channel_videos(isolated_client: YtMeta):
    """
    Tests fetching a small number of videos from a real channel.
    ensuring the end-to-end process works.
    """
    channel_url = "https://www.youtube.com/@TED/videos"
    videos_gen = isolated_client.get_channel_videos(channel_url, max_videos=3)
    videos = list(videos_gen)
    assert len(videos) == 3
    for video in videos:
        assert "video_id" in video
        assert "title" in video


@pytest.mark.integration
def test_get_channel_shorts(isolated_client: YtMeta):
    """
    Tests fetching a small number of shorts from a real channel.
    """
    channel_url = "https://www.youtube.com/@bashbunni"
    shorts_gen = isolated_client.get_channel_shorts(channel_url, max_videos=3)
    shorts = list(shorts_gen)
    assert len(shorts) == 3
    for short in shorts:
        assert "video_id" in short
        assert "title" in short
