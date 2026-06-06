from unittest.mock import MagicMock, patch

import pytest

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


def test_m21_channel_metadata_via_http_layer_mock():
    """M21: most channel-fetcher tests mock private methods
    (_get_channel_page_data, _get_continuation_data), so a refactor of
    those internals silently invalidates the tests without catching
    real breakage. This test mocks at the HTTP layer instead — via
    httpx.MockTransport — so the REAL ytcfg/initialData extraction and
    parse_channel_metadata path runs end-to-end against a controlled
    response. It's the pattern the review recommends; it exercises the
    code that actually changes when YouTube's page shape changes.
    """
    import httpx

    from tests.conftest import make_mock_html
    from yt_meta.fetchers import ChannelFetcher, VideoFetcher

    initial_data = {
        "metadata": {
            "channelMetadataRenderer": {
                "title": "MockTransport Channel",
                "description": "via httpx.MockTransport",
                "externalId": "UCmocktransport0000000",
                "isFamilySafe": True,
            }
        }
    }
    ytcfg = {"INNERTUBE_API_KEY": "k", "INNERTUBE_CONTEXT": {}}
    html = make_mock_html(None, initial_data, ytcfg)

    def handler(request: httpx.Request) -> httpx.Response:
        # Real code under test built this URL from the channel_url;
        # assert it's pointed at the videos tab as expected.
        assert request.url.path.endswith("/videos")
        return httpx.Response(200, text=html)

    session = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        fetcher = ChannelFetcher(
            session=session,
            cache={},
            video_fetcher=VideoFetcher(session=session, cache={}),
        )
        metadata = fetcher.get_channel_metadata(
            "https://www.youtube.com/@mocktransport/videos"
        )
    finally:
        session.close()

    assert metadata["title"] == "MockTransport Channel"
    assert metadata["channel_id"] == "UCmocktransport0000000"


def test_l5_run_filtered_pipeline_in_isolation():
    """L5: the filter-pipeline epilogue (partition → must_fetch decision
    → _process_videos loop) was hand-copied across get_channel_videos,
    get_channel_shorts, and get_playlist_videos. L5 extracts it into a
    module-level ``_run_filtered_pipeline`` generator that's testable
    without constructing a fetcher, mocking HTTP, or touching the
    network — which is the whole point of the extraction.

    Fast-filter-only path: no full-metadata fetch needed, so
    video_fetcher must never be called.
    """
    from unittest.mock import MagicMock

    from yt_meta.fetchers import _run_filtered_pipeline

    raw = iter(
        [
            {"video_id": "a", "view_count": 50},
            {"video_id": "b", "view_count": 5000},
            {"video_id": "c", "view_count": 100},
        ]
    )
    video_fetcher = MagicMock()
    video_fetcher.get_video_metadata.side_effect = AssertionError(
        "fast-filter-only pipeline must not fetch full metadata"
    )

    result = list(
        _run_filtered_pipeline(
            raw,
            filters={"view_count": {"gte": 100}},
            content_type="videos",
            fetch_full_metadata=False,
            video_fetcher=video_fetcher,
            logger=MagicMock(),
            stop_at_video_id=None,
            max_videos=-1,
        )
    )

    assert [v["video_id"] for v in result] == ["b", "c"]


def test_l5_run_filtered_pipeline_respects_max_videos():
    """L5: the max_videos early-stop lives in the extracted pipeline."""
    from unittest.mock import MagicMock

    from yt_meta.fetchers import _run_filtered_pipeline

    raw = iter([{"video_id": str(i)} for i in range(10)])
    result = list(
        _run_filtered_pipeline(
            raw,
            filters=None,
            content_type="videos",
            fetch_full_metadata=False,
            video_fetcher=MagicMock(),
            logger=MagicMock(),
            stop_at_video_id=None,
            max_videos=3,
        )
    )
    assert [v["video_id"] for v in result] == ["0", "1", "2"]


def test_l5_run_filtered_pipeline_slow_filter_fetches_full_metadata():
    """L5: a slow filter forces full-metadata fetch and applies the
    slow filter to the merged dict — all inside the extracted helper.
    """
    from unittest.mock import MagicMock

    from yt_meta.fetchers import _run_filtered_pipeline

    raw = iter([{"video_id": "a"}, {"video_id": "b"}])
    video_fetcher = MagicMock()
    # 'a' has like_count below the threshold, 'b' above
    video_fetcher.get_video_metadata.side_effect = [
        {"like_count": 10},
        {"like_count": 5000},
    ]

    result = list(
        _run_filtered_pipeline(
            raw,
            filters={"like_count": {"gte": 1000}},
            content_type="videos",
            fetch_full_metadata=False,  # auto-enabled by the slow filter
            video_fetcher=video_fetcher,
            logger=MagicMock(),
            stop_at_video_id=None,
            max_videos=-1,
        )
    )
    assert [v["video_id"] for v in result] == ["b"]
    assert video_fetcher.get_video_metadata.call_count == 2


def test_get_channel_metadata_unit(
    channel_fetcher, mocker, bulwark_channel_initial_data, bulwark_channel_ytcfg
):
    mocker.patch.object(
        channel_fetcher,
        "_get_channel_page_data",
        return_value=(bulwark_channel_initial_data, bulwark_channel_ytcfg),
    )
    metadata = channel_fetcher.get_channel_metadata("https://any-url.com")
    assert metadata is not None
    assert metadata["title"] == "The Bulwark"


@patch(
    "yt_meta.fetchers.ChannelFetcher._get_channel_page_data",
    return_value=(None, None),
)
def test_get_channel_videos_raises_for_bad_initial_data(
    mock_get_page_data, channel_fetcher
):
    with pytest.raises(
        MetadataParsingError, match="Could not find initial data script in channel page"
    ):
        list(channel_fetcher.get_channel_videos("test_channel"))


def test_m3_shorts_generator_survives_empty_parse_result(channel_fetcher, mocker):
    """REGRESSION (M3): _get_raw_shorts_generator called
    ``parsing.extract_shorts_from_renderers([renderer])[0][0]`` without
    checking whether the parser returned an empty list. If YouTube
    introduces a richItemRenderer variant that the parser doesn't
    classify as a Short (in-feed ads/promos, A/B-test wrappers,
    future content types), the parser returns ``([], None)`` and the
    [0][0] index raises IndexError — silently killing the entire shorts
    generator for the channel.

    Defensive guard checks shorts is non-empty before indexing.
    """
    from yt_meta import parsing

    # Force the parser to return empty even though the renderer "looks
    # valid" to the surrounding ``if not video_data: continue`` guard
    mocker.patch.object(
        parsing, "extract_shorts_from_renderers", return_value=([], None)
    )

    mocker.patch.object(
        channel_fetcher,
        "_get_channel_shorts_page_data",
        return_value=(
            {
                "contents": {
                    "twoColumnBrowseResultsRenderer": {
                        "tabs": [
                            {
                                "tabRenderer": {
                                    "selected": True,
                                    "title": "Shorts",
                                    "content": {
                                        "richGridRenderer": {
                                            "contents": [
                                                {
                                                    "richItemRenderer": {
                                                        "content": {
                                                            "shortsLockupViewModel": {
                                                                "ok": True
                                                            }
                                                        }
                                                    }
                                                }
                                            ]
                                        }
                                    },
                                }
                            }
                        ]
                    }
                }
            },
            {"INNERTUBE_API_KEY": "k"},
        ),
    )

    # The current bug raises IndexError before producing any result.
    # After fix, the generator runs to completion yielding nothing.
    result = list(
        channel_fetcher.get_channel_shorts(
            "https://www.youtube.com/@test/shorts"
        )
    )
    assert result == []


def test_get_channel_videos_handles_continuation_errors(
    channel_fetcher, mocker, youtube_channel_initial_data, youtube_channel_ytcfg
):
    mocker.patch.object(
        channel_fetcher,
        "_get_channel_page_data",
        return_value=(
            youtube_channel_initial_data,
            youtube_channel_ytcfg,
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
