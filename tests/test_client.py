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
        return_value=(bulwark_channel_initial_data, bulwark_channel_ytcfg),
    )
    metadata = client.get_channel_metadata("https://any-url.com")
    assert metadata is not None
    assert metadata["title"] == "The Bulwark"


def test_get_video_metadata_live_stream_unit(client):
    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value.text = get_fixture("live_stream.html")
        mock_get.return_value.status_code = 200
        result = client.get_video_metadata("dQw4w9WgXcQ")
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
    return_value=(None, None),
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


def test_regression_m17_get_video_comments_accepts_youtu_be_url(client, mocker):
    """REGRESSION (M17): the Facade previously called
    VideoFetcher.get_video_id, which crashed on `youtu.be/` URLs. The Facade
    now uses utils.extract_video_id directly, so the common short-form URL
    works end-to-end.
    """
    seen_video_ids = []

    def fake_get_comments(video_id, **kwargs):
        seen_video_ids.append(video_id)
        return iter([])

    mocker.patch.object(
        client._comment_fetcher, "get_comments", side_effect=fake_get_comments
    )

    list(client.get_video_comments("https://youtu.be/dQw4w9WgXcQ", limit=0))

    assert seen_video_ids == ["dQw4w9WgXcQ"]


def test_h14_default_sort_for_get_video_comments_is_recent(client, mocker):
    """H14 (default-sort half): README declares sort_by=SORT_BY_RECENT as the
    documented default (README.md:451, :454), but client.py defaulted to 'top'.
    yt-meta is a metadata-retrieval tool; the raw chronological stream is the
    appropriate default. 'Top' is YouTube's editorial ranking, which is an
    opt-in concern. Flipping the default also makes since_date short-circuit
    pagination out of the box.
    """
    seen_kwargs = {}

    def fake_get_comments(video_id, **kwargs):
        seen_kwargs.update(kwargs)
        return iter([])

    mocker.patch.object(
        client._comment_fetcher, "get_comments", side_effect=fake_get_comments
    )

    list(client.get_video_comments("dQw4w9WgXcQ", limit=0))

    assert seen_kwargs["sort_by"] == "recent"


def test_h14_default_sort_for_get_video_comments_with_reply_tokens_is_recent(
    client, mocker
):
    """Same as test_h14_default_sort_for_get_video_comments_is_recent but for
    the reply-token variant. Defaults must stay aligned across both Facade
    comment entrypoints.
    """
    seen_kwargs = {}

    def fake_get_comments(video_id, **kwargs):
        seen_kwargs.update(kwargs)
        return iter([])

    mocker.patch.object(
        client._comment_fetcher, "get_comments", side_effect=fake_get_comments
    )

    list(client.get_video_comments_with_reply_tokens("dQw4w9WgXcQ", limit=0))

    assert seen_kwargs["sort_by"] == "recent"


def test_m19_filters_kwarg_threaded_to_comment_fetcher(client, mocker):
    """M19: client.get_video_comments accepts a `filters` dict and forwards
    it to CommentFetcher.get_comments. Operates on the in-memory comment list
    after fetching (most comment filters cannot short-circuit pagination).
    """
    seen_kwargs = {}

    def fake_get_comments(video_id, **kwargs):
        seen_kwargs.update(kwargs)
        return iter([])

    mocker.patch.object(
        client._comment_fetcher, "get_comments", side_effect=fake_get_comments
    )

    filters = {"is_by_owner": {"eq": True}}
    list(client.get_video_comments("dQw4w9WgXcQ", limit=10, filters=filters))

    assert seen_kwargs["filters"] == filters


def test_m19_invalid_filter_field_raises_valueerror(client):
    """M19: validate_filters runs before any network request. An unknown
    filter field fails fast — matches README:297 ('validates filters before
    making any network requests').
    """
    with pytest.raises(ValueError, match="Unknown filter field"):
        list(
            client.get_video_comments(
                "dQw4w9WgXcQ", limit=10, filters={"nonexistent_field": {"eq": True}}
            )
        )


def test_m19_unbounded_limit_without_since_date_raises_valueerror(client):
    """M19 safety guard: unbounded fetching (limit=None or limit=-1) without
    a `since_date` time-bound can produce millions of requests on popular
    videos. Force the caller to opt in to a bound. Aligns with the project's
    'minimal requests' value.
    """
    with pytest.raises(ValueError, match="since_date"):
        list(client.get_video_comments("dQw4w9WgXcQ", limit=None))
    with pytest.raises(ValueError, match="since_date"):
        list(client.get_video_comments("dQw4w9WgXcQ", limit=-1))


def test_m19_unbounded_limit_with_since_date_is_allowed(client, mocker):
    """M19 safety guard: unbounded fetching IS allowed when `since_date` is
    set, because the short-circuit on the sort_by='recent' default caps the
    total request count.
    """
    mocker.patch.object(
        client._comment_fetcher, "get_comments", return_value=iter([])
    )
    list(
        client.get_video_comments(
            "dQw4w9WgXcQ", limit=None, since_date="2025-01-01"
        )
    )


def test_m19_get_video_comments_with_reply_tokens_also_guards(client):
    """M19 safety guard applies symmetrically to the reply-tokens variant.
    A `since_date` kwarg is also added to this method so the guard has an
    escape hatch.
    """
    with pytest.raises(ValueError, match="since_date"):
        list(client.get_video_comments_with_reply_tokens("dQw4w9WgXcQ", limit=-1))


def test_h13_ytmeta_accepts_cache_kwarg_with_mutablemapping():
    """H13: README (README.md:281, :439) documents
    `YtMeta(cache=persistent_cache)` accepting any MutableMapping, but the
    real constructor only took `cache_path: str`. Copy-pasting the README
    example raised TypeError. The widened constructor accepts both
    `cache_path` and `cache=`; precedence is `cache` over `cache_path` over
    DummyCache.
    """
    my_cache: dict = {}
    c = YtMeta(cache=my_cache)
    assert c.cache is my_cache


def test_h13_ytmeta_constructor_still_accepts_cache_path(tmp_path):
    """H13: backward compatibility — existing `YtMeta(cache_path='...')`
    callers continue to work unchanged.
    """
    from yt_meta.caching import SQLiteCache

    cache_file = tmp_path / "cache.db"
    c = YtMeta(cache_path=str(cache_file))
    assert isinstance(c.cache, SQLiteCache)


def test_h13_ytmeta_with_no_cache_args_uses_dummycache():
    """H13: with neither kwarg, caching stays disabled (DummyCache)."""
    from yt_meta.caching import DummyCache

    c = YtMeta()
    assert isinstance(c.cache, DummyCache)


def test_m10_ytmeta_exposes_cache_ttl_seconds(tmp_path):
    """M10: SQLiteCache supports a per-instance TTL (default 86400 s, 1
    day) but YtMeta never surfaced it — the constructor unconditionally
    used the SQLiteCache default. Expose `cache_ttl_seconds` on YtMeta so
    callers can pick a TTL appropriate to their workload (long for
    video_meta — effectively immutable; short for channel_page — fresh
    uploads). This is the user-facing knob; per-prefix TTL is the
    follow-up Longer-term #4 work.
    """
    cache_file = tmp_path / "cache.db"
    c = YtMeta(cache_path=str(cache_file), cache_ttl_seconds=60)
    assert c.cache.ttl_seconds == 60


def test_m10_default_cache_ttl_is_one_day(tmp_path):
    """M10: backward compat — the default TTL is 86400 (1 day) when not
    specified. Matches SQLiteCache's own default.
    """
    cache_file = tmp_path / "cache.db"
    c = YtMeta(cache_path=str(cache_file))
    assert c.cache.ttl_seconds == 86400


def test_h5_ytmeta_is_a_context_manager_closing_session():
    """H5: YtMeta owns an httpx.Client (and historically a CommentAPIClient
    httpx.Client and a SQLite connection). None of them were reliably
    closed — the comment client relied on __del__ (unreliable at
    interpreter shutdown / reference cycles) and YtMeta had no close()
    at all. Now `with YtMeta() as client:` closes everything on exit.
    """
    with YtMeta() as c:
        assert not c.session.is_closed
    assert c.session.is_closed


def test_h5_explicit_close_works_too():
    """H5: not every codebase wants a context manager. `client.close()`
    must work as the explicit cleanup entry point.
    """
    c = YtMeta()
    assert not c.session.is_closed
    c.close()
    assert c.session.is_closed


def test_h5_close_is_idempotent():
    """H5: calling close() twice (e.g. inside __exit__ after an explicit
    close in the body) must not raise.
    """
    c = YtMeta()
    c.close()
    c.close()  # must not raise


def test_h5_close_cascades_to_comment_fetcher_client():
    """H5: YtMeta.close() must reach into the comment subsystem and
    close its private httpx.Client. Until M1/L2 unifies the comment
    subsystem under the main session, the comment client is a separate
    owned resource and must be tracked.
    """
    c = YtMeta()
    inner_client = c._comment_fetcher.api_client.client
    assert not inner_client.is_closed
    c.close()
    assert inner_client.is_closed


def test_h5_close_closes_sqlite_cache(tmp_path):
    """H5: when YtMeta owns a SQLiteCache (cache_path given), close()
    must close the SQLite connection. On Windows this releases the
    .db file lock; on every OS it returns the file descriptor.
    """
    import sqlite3

    cache_file = tmp_path / "cache.db"
    c = YtMeta(cache_path=str(cache_file))
    c.cache["k"] = "v"
    c.close()
    # After close, operations on the cache must fail. sqlite3 raises
    # ProgrammingError ("Cannot operate on a closed database").
    with pytest.raises(sqlite3.ProgrammingError):
        c.cache["other"] = "x"


def test_m12_comment_classes_have_no_del_hooks():
    """REGRESSION (M12): __del__ on CommentFetcher and CommentAPIClient
    was the only cleanup path — unreliable at interpreter shutdown,
    skipped on reference cycles, suppressed exceptions silently. With
    H5's explicit close()/__enter__/__exit__ in place, __del__ is now
    redundant AND actively harmful. Remove it. Defense-in-depth: this
    test guards against a future refactor silently re-adding it.
    """
    from yt_meta.comment_api_client import CommentAPIClient
    from yt_meta.comment_fetcher import CommentFetcher

    assert "__del__" not in vars(CommentFetcher), (
        "CommentFetcher.__del__ removed by M12; explicit close() is the "
        "only cleanup path"
    )
    assert "__del__" not in vars(CommentAPIClient), (
        "CommentAPIClient.__del__ removed by M12; explicit close() is "
        "the only cleanup path"
    )


def test_m12_comment_classes_have_explicit_close():
    """REGRESSION (M12): the replacement for __del__ is explicit close()
    on both classes. CommentFetcher.close() delegates to its
    CommentAPIClient; CommentAPIClient.close() closes its httpx.Client.
    """
    from yt_meta.comment_api_client import CommentAPIClient
    from yt_meta.comment_fetcher import CommentFetcher

    cf = CommentFetcher()
    ac = cf.api_client
    assert hasattr(cf, "close") and callable(cf.close)
    assert hasattr(ac, "close") and callable(ac.close)

    cf.close()
    assert ac.client.is_closed

    # Idempotent
    cf.close()
    ac.close()


def test_m14_internal_classes_no_longer_re_exported():
    """REGRESSION (M14): CommentAPIClient, CommentParser, and the
    BestCommentFetcher alias were re-exported from the top-level
    package, exposing implementation details as public API. The
    review's v0.6.0 plan removes them. Anyone who needs the internals
    can still import from the submodule directly
    (yt_meta.comment_api_client / yt_meta.comment_parser); top-level
    `from yt_meta import X` now raises ImportError.
    """
    with pytest.raises(ImportError):
        from yt_meta import CommentAPIClient  # noqa: F401
    with pytest.raises(ImportError):
        from yt_meta import CommentParser  # noqa: F401
    with pytest.raises(ImportError):
        from yt_meta import BestCommentFetcher  # noqa: F401


def test_m14_internal_submodule_imports_still_work():
    """REGRESSION (M14): removing the re-exports doesn't break the
    submodules themselves — power users can still reach the internals
    if they really need to, via the documented submodule path.
    """
    from yt_meta.comment_api_client import CommentAPIClient  # noqa: F401
    from yt_meta.comment_fetcher import CommentFetcher  # noqa: F401
    from yt_meta.comment_parser import CommentParser  # noqa: F401


def test_m14_public_surface_unchanged():
    """REGRESSION (M14): the legitimate public surface stays exactly the
    same — YtMeta, CommentFetcher, the exceptions, and the
    parse_relative_date_string helper.
    """
    from yt_meta import (  # noqa: F401
        CommentFetcher,
        MetadataParsingError,
        VideoUnavailableError,
        YtMeta,
        parse_relative_date_string,
    )
