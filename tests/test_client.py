from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import get_fixture
from yt_meta.client import YtMeta
from yt_meta.exceptions import MetadataParsingError, VideoUnavailableError

# Define the path to our test fixture
FIXTURE_PATH = "tests/fixtures"
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
    mocker.patch(
        "yt_meta.fetchers.VideoFetcher.get_video_metadata",
        side_effect=VideoUnavailableError("Video is private"),
    )
    with pytest.raises(VideoUnavailableError, match="Video is private"):
        client.get_video_metadata("dQw4w9WgXcQ")


def test_get_channel_metadata_unit(
    client, mocker, bulwark_channel_initial_data, bulwark_channel_ytcfg
):
    """
    Tests that channel metadata can be parsed correctly from a fixture file.
    """
    mocker.patch(
        "yt_meta.fetchers.ChannelFetcher._get_channel_page_data",
        return_value=(bulwark_channel_initial_data, bulwark_channel_ytcfg, None),
    )
    metadata = client.get_channel_metadata("https://any-url.com")
    assert metadata is not None
    assert metadata["title"] == "The Bulwark"


def test_get_video_metadata_live_stream_unit(client):
    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value.text = get_fixture("live_stream.html")
        mock_get.return_value.status_code = 200
        result = client.get_video_metadata("LIVE_STREAM_VIDEO_ID")
        assert result is None, "Should return None for unparseable live stream pages"


def test_get_channel_page_data_fails_on_request_error_unit(client, mocker):
    mocker.patch(
        "yt_meta.fetchers.ChannelFetcher._get_channel_page_data",
        side_effect=VideoUnavailableError("Test error"),
    )
    with pytest.raises(VideoUnavailableError):
        client.get_channel_metadata("test_channel")


@patch(
    "yt_meta.fetchers.ChannelFetcher._get_channel_page_data",
    return_value=(None, None, "bad data"),
)
def test_get_channel_videos_raises_for_bad_initial_data_unit(
    mock_get_page_data, client
):
    with pytest.raises(
        MetadataParsingError, match="Could not find initial data script in channel page"
    ):
        list(client.get_channel_videos("test_channel"))


def test_get_channel_videos_handles_continuation_errors_unit(
    client, mocker, youtube_channel_initial_data, youtube_channel_ytcfg
):
    mocker.patch(
        "yt_meta.fetchers.ChannelFetcher._get_channel_page_data",
        return_value=(
            youtube_channel_initial_data,
            youtube_channel_ytcfg,
            "<html></html>",
        ),
    )
    mocker.patch(
        "yt_meta.fetchers.ChannelFetcher._get_continuation_data", return_value=None
    )
    videos = list(client.get_channel_videos("https://any-url.com"))
    assert len(videos) == 30


def test_get_channel_videos_paginates_correctly_unit(client):
    with (
        patch.object(
            client._channel_fetcher, "_get_continuation_data"
        ) as mock_continuation,
        patch.object(
            client._channel_fetcher, "_get_channel_page_data"
        ) as mock_get_page_data,
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
        videos = list(client.get_channel_videos("https://any-url.com"))
        assert len(videos) == 2


def test_ytmeta_initialization():
    """Test YtMeta initialization without a cache."""
    client = YtMeta()
    from yt_meta.caching import DummyCache

    assert isinstance(client.cache, DummyCache)


def test_ytmeta_initialization_with_cache():
    """Test YtMeta initialization with a cache object."""
    client = YtMeta(cache_path="dummy.db")
    assert client.cache is not None
    from yt_meta.caching import SQLiteCache

    assert isinstance(client.cache, SQLiteCache)


def test_clear_cache(tmp_path):
    """Test clearing the cache."""
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    client.cache["key1"] = "value1"
    client.cache["key2"] = "value2"
    assert len(client.cache) == 2
    client.clear_cache()
    assert len(client.cache) == 0


def test_clear_cache_prefix(tmp_path):
    """Test clearing the cache with a prefix."""
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    client.cache["video:abc"] = "value1"
    client.cache["video:def"] = "value2"
    client.cache["channel:xyz"] = "value3"
    assert len(client.cache) == 3
    client.clear_cache(prefix="video:")
    assert len(client.cache) == 1
    assert "channel:xyz" in client.cache
    assert "video:abc" not in client.cache


def test_clear_cache_all(tmp_path):
    """Test clearing the cache with a prefix."""
    cache_file = tmp_path / "cache.db"
    client = YtMeta(cache_path=str(cache_file))
    client.cache["video:abc"] = "value1"
    client.cache["video:def"] = "value2"
    client.clear_cache(prefix="video:")
    assert len(client.cache) == 0


# --- Live Integration Tests ---
@pytest.mark.integration
def test_get_channel_metadata_live(isolated_client: YtMeta):
    """Test fetching metadata for a live channel."""
    channel_url = "https://www.youtube.com/@LofiGirl"
    metadata = isolated_client.get_channel_metadata(channel_url=channel_url)
    assert metadata["title"] == "Lofi Girl"
    assert metadata["channel_id"] is not None


@pytest.mark.integration
def test_get_channel_videos_live(isolated_client: YtMeta):
    """Test fetching videos for a live channel."""
    channel_url = "https://www.youtube.com/@MrBeast/videos"
    videos = isolated_client.get_channel_videos(channel_url=channel_url, max_videos=5)
    video_list = list(videos)
    assert len(video_list) == 5
    assert "video_id" in video_list[0]


@pytest.mark.integration
def test_get_channel_shorts_live(isolated_client: YtMeta):
    """Test fetching shorts for a live channel."""
    channel_url = "https://www.youtube.com/@MrBeast"
    shorts = isolated_client.get_channel_shorts(channel_url=channel_url, max_videos=5)
    short_list = list(shorts)
    assert len(short_list) == 5
    assert "video_id" in short_list[0]


@pytest.mark.integration
def test_get_playlist_videos_live(isolated_client: YtMeta):
    """Test fetching videos for a live playlist."""
    playlist_id = (
        "PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo"  # Crash Course Computer Science - stable
    )
    videos = isolated_client.get_playlist_videos(playlist_id=playlist_id, max_videos=5)
    video_list = list(videos)
    assert len(video_list) >= 1  # Check for at least one video
    assert "video_id" in video_list[0]


@pytest.mark.integration
def test_get_comments_live(isolated_client: YtMeta):
    """Test fetching comments for a live video."""
    video_id = "jNQXAC9IVRw"  # "Me at the zoo" - very stable, lots of comments
    comments = isolated_client.comment_fetcher.get_comments(video_id=video_id, limit=10)
    comment_list = list(comments)
    assert len(comment_list) >= 1
    assert "text" in comment_list[0]


@pytest.mark.integration
def test_get_comment_replies_live(isolated_client: YtMeta):
    """Test fetching replies for a live comment."""
    video_id = "jNQXAC9IVRw"  # "Me at the zoo"
    # Scan more comments to find one with replies, this is more robust
    comments_gen = isolated_client.comment_fetcher.get_comments(
        video_id=video_id, limit=50, include_reply_continuation=True
    )

    found_replies = False
    for comment in comments_gen:
        if "reply_continuation_token" in comment:
            replies = isolated_client.comment_fetcher.get_comment_replies(
                video_id=video_id,
                reply_continuation_token=comment["reply_continuation_token"],
                limit=1,
            )
            reply_list = list(replies)
            if reply_list:
                assert "text" in reply_list[0]
                found_replies = True
                break

    assert found_replies, (
        "Could not find any comments with replies in the first 50 comments."
    )
