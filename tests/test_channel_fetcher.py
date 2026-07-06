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


def test_get_channel_streams_parses_lockup_grid(channel_fetcher, mocker):
    """get_channel_streams fetches the Live (/streams) tab and parses its
    lockupViewModel grid — the same shape as Videos. Exercised against a
    captured @AppleDeveloper/streams page (all upcoming WWDC streams)."""
    import json
    from pathlib import Path

    fixture = (
        Path(__file__).parent / "fixtures" / "channel_streams_lockup_renderers.json"
    )
    renderers = json.loads(fixture.read_text())["contents"]
    initial_data = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "selected": True,
                            "title": "Live",
                            "content": {"richGridRenderer": {"contents": renderers}},
                        }
                    }
                ]
            }
        }
    }
    mocker.patch.object(
        channel_fetcher,
        "_get_channel_streams_page_data",
        return_value=(initial_data, {"INNERTUBE_API_KEY": "k"}),
    )

    streams = list(channel_fetcher.get_channel_streams("https://www.youtube.com/@x"))
    assert streams
    for s in streams:
        assert s["video_id"] and len(s["video_id"]) == 11
        assert s["is_upcoming"] is True
        assert "Scheduled for" in s["scheduled_text"]


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


def test_c8_get_channel_videos_accepts_datetime_start_date():
    """REGRESSION (C8, 2026-07-05 review): get_channel_videos(
    start_date=datetime.now()) raised TypeError mid-pagination at the
    date short-circuit comparison. Driven through the real HTTP layer
    (R1) with real captured lockupViewModel renderers, so the real
    parser produces publish_date and the real comparison runs (R6:
    date-kwarg × pagination-short-circuit interaction)."""
    import json
    from datetime import datetime
    from pathlib import Path

    import httpx

    from tests.conftest import make_mock_html

    renderers = json.loads(
        (
            Path(__file__).parent / "fixtures" / "channel_videos_lockup_renderers.json"
        ).read_text()
    )["contents"]
    # Single-page scenario: drop the fixture's continuation renderer so
    # the generator ends after the initial page.
    renderers = [r for r in renderers if "continuationItemRenderer" not in r]
    initial_data = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "selected": True,
                            "title": "Videos",
                            "content": {"richGridRenderer": {"contents": renderers}},
                        }
                    }
                ]
            }
        }
    }
    html = make_mock_html(None, initial_data)
    session = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=html))
    )
    try:
        fetcher = ChannelFetcher(
            session=session,
            cache={},
            video_fetcher=VideoFetcher(session=session, cache={}),
        )
        # Must not raise TypeError; a recent datetime start_date simply
        # filters out the fixture's older videos.
        videos = list(
            fetcher.get_channel_videos(
                "https://www.youtube.com/@x", start_date=datetime(2020, 1, 1, 8, 0)
            )
        )
        assert isinstance(videos, list)
    finally:
        session.close()


def test_me_missing_fast_filter_field_defers_to_hydration():
    """REGRESSION (M-e, 2026-07-05 review) / R6 interaction (fast
    filters × full-metadata hydration): a fast-filter field missing on
    the raw item (e.g. publish_date on a page shape without date text)
    dropped the video BEFORE hydration — even when fetch_full_metadata
    =True guaranteed the field one request later. Result: date-filtered
    playlists could return 0 items with no error. When hydration is on,
    a missing-field fast filter must be deferred to the merged dict."""
    from datetime import date, datetime
    from unittest.mock import MagicMock

    from yt_meta.fetchers import _run_filtered_pipeline

    raw = iter([{"video_id": "a", "publish_date": None}])
    video_fetcher = MagicMock()
    video_fetcher.get_video_metadata.return_value = {
        "publish_date": datetime(2024, 1, 2)
    }

    result = list(
        _run_filtered_pipeline(
            raw,
            filters={"publish_date": {"gte": date(2024, 1, 1)}},
            content_type="videos",
            fetch_full_metadata=True,
            video_fetcher=video_fetcher,
            logger=MagicMock(),
            stop_at_video_id=None,
            max_videos=-1,
        )
    )
    assert [v["video_id"] for v in result] == ["a"], (
        "item dropped before hydration could supply the filter field"
    )


def test_option_a_hydration_upgrades_precision_and_keeps_listing_text():
    """Option A (R6 merge interaction): fetch_full_metadata=True
    replaces the approximate date with the exact one and upgrades the
    marker — but the listing's raw text must SURVIVE the merge (the
    watch page has none), so even exact records show what the listing
    claimed."""
    from datetime import datetime
    from unittest.mock import MagicMock

    from yt_meta.fetchers import _run_filtered_pipeline

    raw = iter(
        [
            {
                "video_id": "a",
                "publish_date": datetime(2023, 7, 5, 23, 45),
                "publish_date_precision": "approximate",
                "publish_date_text": "3 years ago",
            }
        ]
    )
    video_fetcher = MagicMock()
    video_fetcher.get_video_metadata.return_value = {
        "publish_date": datetime(2023, 7, 5, 8, 0, 29),
        "publish_date_precision": "exact",
        "publish_date_text": None,
    }
    result = list(
        _run_filtered_pipeline(
            raw,
            filters=None,
            content_type="videos",
            fetch_full_metadata=True,
            video_fetcher=video_fetcher,
            logger=MagicMock(),
            stop_at_video_id=None,
            max_videos=-1,
        )
    )
    (v,) = result
    assert v["publish_date"] == datetime(2023, 7, 5, 8, 0, 29)
    assert v["publish_date_precision"] == "exact"
    assert v["publish_date_text"] == "3 years ago"


def test_hour_bounds_without_hydration_raise():
    """REGRESSION: hour-level publish_date bounds are meaningless
    against approximate listing dates. Without fetch_full_metadata=True
    the pipeline must refuse loudly, not return silently-wrong results."""
    from datetime import datetime
    from unittest.mock import MagicMock

    import pytest as _pytest

    from yt_meta.fetchers import _run_filtered_pipeline

    raw = iter([{"video_id": "a", "publish_date": datetime(2023, 7, 5, 23, 45)}])
    with _pytest.raises(ValueError, match="fetch_full_metadata"):
        list(
            _run_filtered_pipeline(
                raw,
                filters={"publish_date": {"gte": datetime(2023, 7, 5, 8, 0)}},
                content_type="videos",
                fetch_full_metadata=False,
                video_fetcher=MagicMock(),
                logger=MagicMock(),
                stop_at_video_id=None,
                max_videos=-1,
            )
        )


def test_padded_coarse_cut_hydrates_near_boundary_videos():
    """REGRESSION (funnel padding): a video whose APPROXIMATE date fell
    2 months before start_date was dropped before hydration — even
    though its exact date is inside the window and '3 years ago' text
    has ~±6 months of rounding error. When hydrating, the approximate
    cut must be padded by the text's granularity; the exact post-merge
    check tightens."""
    from datetime import date, datetime
    from unittest.mock import MagicMock

    from yt_meta.fetchers import _run_filtered_pipeline

    raw = iter(
        [
            {   # approximate date 2 months BEFORE the window, year-granular
                "video_id": "near",
                "publish_date": datetime(2023, 5, 1, 23, 45),
                "publish_date_precision": "approximate",
                "publish_date_text": "3 years ago",
            },
            {   # approximate date a full year before — outside any pad
                "video_id": "far",
                "publish_date": datetime(2022, 7, 1, 23, 45),
                "publish_date_precision": "approximate",
                "publish_date_text": "4 years ago",
            },
        ]
    )
    video_fetcher = MagicMock()
    video_fetcher.get_video_metadata.return_value = {
        "video_id": "near",
        "publish_date": datetime(2023, 7, 10, 9, 30),  # exact: IN window
        "publish_date_precision": "exact",
        "publish_date_text": None,
    }
    result = list(
        _run_filtered_pipeline(
            raw,
            filters={"publish_date": {"gte": date(2023, 7, 1), "lte": date(2023, 7, 31)}},
            content_type="videos",
            fetch_full_metadata=True,
            video_fetcher=video_fetcher,
            logger=MagicMock(),
            stop_at_video_id=None,
            max_videos=-1,
        )
    )
    assert [v["video_id"] for v in result] == ["near"]
    # 'far' must not even be hydrated — the padded coarse cut excludes it
    assert video_fetcher.get_video_metadata.call_count == 1


def test_padded_early_stop_paginates_past_approximate_boundary():
    """REGRESSION (funnel padding, pagination side): the chronological
    early-stop compared the APPROXIMATE date against start_date raw —
    a page-1 video whose '3 years ago' date resolved 45 days before the
    window stopped pagination dead, so the page-2 video whose EXACT
    date IS in the window was never fetched. When hydrating, the stop
    boundary must be padded by the approximate date's granularity.

    R1: full HTTP layer via MockTransport (channel page GET →
    continuation POST → per-video watch GETs); lockups derived from the
    captured fixture with controlled date text."""
    import copy
    import json
    from datetime import date, datetime, timedelta
    from pathlib import Path
    from urllib.parse import parse_qs, urlparse

    import httpx

    from tests.conftest import make_mock_html

    base = json.loads(
        (
            Path(__file__).parent / "fixtures" / "channel_videos_lockup_renderers.json"
        ).read_text()
    )["contents"]
    proto = copy.deepcopy(
        next(r for r in base if "richItemRenderer" in r)
    )

    def lockup_item(video_id):
        item = copy.deepcopy(proto)
        lvm = item["richItemRenderer"]["content"]["lockupViewModel"]
        lvm["contentId"] = video_id
        lvm["metadata"]["lockupMetadataViewModel"]["metadata"][
            "contentMetadataViewModel"
        ]["metadataRows"] = [
            {
                "metadataParts": [
                    {"text": {"content": "12K views"}},
                    {"text": {"content": "3 years ago"}},
                ]
            }
        ]
        return item

    today = date.today()
    window_start = today - timedelta(days=3 * 365) + timedelta(days=45)
    window_end = today - timedelta(days=3 * 365) + timedelta(days=75)
    exact_dt = datetime.combine(
        today - timedelta(days=3 * 365) + timedelta(days=60), datetime.min.time()
    ).replace(hour=9)

    page1 = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "selected": True,
                            "title": "Videos",
                            "content": {
                                "richGridRenderer": {
                                    "contents": [
                                        lockup_item("vidpage1xxx"),
                                        {
                                            "continuationItemRenderer": {
                                                "continuationEndpoint": {
                                                    "continuationCommand": {"token": "T2"}
                                                }
                                            }
                                        },
                                    ]
                                }
                            },
                        }
                    }
                ]
            }
        }
    }
    page2 = {
        "onResponseReceivedActions": [
            {
                "appendContinuationItemsAction": {
                    "continuationItems": [lockup_item("vidpage2xxx")]
                }
            }
        ]
    }

    def watch_html(video_id):
        player = {
            "playabilityStatus": {"status": "OK"},
            "videoDetails": {
                "videoId": video_id,
                "title": "T",
                "author": "A",
                "lengthSeconds": "60",
                "viewCount": "1",
            },
            "microformat": {
                "playerMicroformatRenderer": {
                    "publishDate": exact_dt.isoformat()
                }
            },
        }
        return make_mock_html(player, {"contents": {}})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/watch":
            vid = parse_qs(urlparse(str(request.url)).query)["v"][0]
            return httpx.Response(200, text=watch_html(vid))
        if request.method == "POST":
            return httpx.Response(200, json=page2)
        return httpx.Response(200, text=make_mock_html(None, page1))

    with httpx.Client(transport=httpx.MockTransport(handler)) as session:
        fetcher = ChannelFetcher(
            session=session,
            cache={},
            video_fetcher=VideoFetcher(session=session, cache={}),
        )
        videos = list(
            fetcher.get_channel_videos(
                "https://www.youtube.com/@x",
                start_date=window_start,
                end_date=window_end,
                fetch_full_metadata=True,
            )
        )

    got = {v["video_id"] for v in videos}
    assert "vidpage2xxx" in got, (
        "pagination stopped at the approximate boundary — page 2's "
        "in-window video was never fetched"
    )
    assert got == {"vidpage1xxx", "vidpage2xxx"}
