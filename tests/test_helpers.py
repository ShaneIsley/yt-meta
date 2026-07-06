"""Tests for the 0.8.0 workflow helpers: iter_new_videos,
get_comment_threads, get_videos_published_between."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from yt_meta import YtMeta

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    return YtMeta()


# --- iter_new_videos -------------------------------------------------------


def test_iter_new_videos_excludes_the_marker(client, mocker):
    """Incremental sync: yields newest-first UNTIL since_video_id and
    EXCLUDES the marker itself — get_channel_videos(stop_at_video_id=)
    includes it, which is wrong for 'what's new since last run'."""
    mocker.patch.object(
        client._channel_fetcher,
        "get_channel_videos",
        return_value=iter(
            [{"video_id": "new2"}, {"video_id": "new1"}, {"video_id": "seen"}]
        ),
    )
    got = list(client.iter_new_videos("https://www.youtube.com/@x", since_video_id="seen"))
    assert [v["video_id"] for v in got] == ["new2", "new1"]


def test_iter_new_videos_threads_kwargs_and_marker(client, mocker):
    """The marker must be passed through as stop_at_video_id so
    pagination stops at it (request efficiency), and fetch kwargs
    thread through."""
    fetch = mocker.patch.object(
        client._channel_fetcher, "get_channel_videos", return_value=iter([])
    )
    list(
        client.iter_new_videos(
            "https://www.youtube.com/@x",
            since_video_id="mark1234567",
            fetch_full_metadata=True,
            max_videos=50,
        )
    )
    kwargs = fetch.call_args.kwargs
    assert kwargs["stop_at_video_id"] == "mark1234567"
    assert kwargs["fetch_full_metadata"] is True
    assert kwargs["max_videos"] == 50


def test_iter_new_videos_without_marker_yields_everything(client, mocker):
    """since_video_id=None → plain newest-first stream (bound it with
    max_videos); nothing is excluded."""
    mocker.patch.object(
        client._channel_fetcher,
        "get_channel_videos",
        return_value=iter([{"video_id": "a"}, {"video_id": "b"}]),
    )
    got = list(client.iter_new_videos("https://www.youtube.com/@x"))
    assert [v["video_id"] for v in got] == ["a", "b"]


# --- get_comment_threads ---------------------------------------------------


def _threads_client_with_real_fixture(client, mocker):
    """Drive the REAL comment machinery (parser + reply-token
    extraction) from the captured 'Me at the zoo' first page (R1);
    only the HTTP boundary is scripted."""
    with open(FIXTURES / "comment_first_page_pinned.json") as f:
        page = json.load(f)
    api = client._comment_fetcher.api_client
    mocker.patch.object(api, "get_initial_video_data", return_value=({}, {}))
    mocker.patch.object(
        api, "get_sort_endpoints_flexible", return_value={"top comments": "t"}
    )
    mocker.patch.object(api, "select_sort_endpoint", return_value="t")
    mocker.patch.object(api, "make_api_request", return_value=page)
    mocker.patch.object(api, "extract_continuation_token", return_value=None)
    return client


def test_get_comment_threads_yields_comment_reply_tuples(client, mocker):
    _threads_client_with_real_fixture(client, mocker)
    fake_replies = [{"id": "r1", "is_reply": True}, {"id": "r2", "is_reply": True}]
    replies_mock = mocker.patch.object(
        client,
        "get_comment_replies",
        side_effect=lambda *a, **kw: iter(fake_replies),
    )

    threads = list(
        client.get_comment_threads(
            video_id="jNQXAC9IVRw", limit=5, replies_per_thread=2, sort_by="top"
        )
    )
    assert len(threads) == 5
    for comment, replies in threads:
        assert comment["id"]
        assert isinstance(replies, list)
        if comment.get("reply_continuation_token"):
            assert [r["id"] for r in replies] == ["r1", "r2"]
    # replies fetched only for tokened comments, capped per thread
    for call in replies_mock.call_args_list:
        assert call.kwargs.get("limit") == 2 or call.args[-1] == 2


def test_get_comment_threads_replies_zero_makes_no_reply_requests(client, mocker):
    """replies_per_thread=0 → structure only, zero extra requests."""
    _threads_client_with_real_fixture(client, mocker)
    replies_mock = mocker.patch.object(client, "get_comment_replies")
    threads = list(
        client.get_comment_threads(video_id="jNQXAC9IVRw", limit=3, replies_per_thread=0)
    )
    assert len(threads) == 3
    assert all(replies == [] for _, replies in threads)
    replies_mock.assert_not_called()


# --- get_videos_published_between ------------------------------------------


def _daily_raw_items(n_days, newest=None):
    """n_days of approximate listing items, newest-first, one per day.
    Approximate dates are one day AHEAD of the exact dates (the skew
    observed live on @TED) — exact date of raw item k is
    newest - k days at 08:00."""
    newest = newest or date.today() - timedelta(days=2)
    items = []
    for k in range(n_days):
        exact_day = newest - timedelta(days=k)
        items.append(
            {
                "video_id": f"vid{k:07d}",
                "title": f"video {k}",
                "publish_date": datetime.combine(
                    exact_day + timedelta(days=1), datetime.min.time()
                ),  # approximate: skewed +1 day
                "publish_date_precision": "approximate",
                "publish_date_text": f"{k+2} days ago",
                "_exact": datetime.combine(exact_day, datetime.min.time()).replace(
                    hour=8, minute=0, second=29
                ),
            }
        )
    return items


def _fetcher_for_bisect(client, mocker, raw_items):
    hydrations = []

    def fake_meta(url):
        vid = url.split("v=")[-1]
        item = next(i for i in raw_items if i["video_id"] == vid)
        hydrations.append(vid)
        return {
            "video_id": vid,
            "title": item["title"],
            "publish_date": item["_exact"],
            "publish_date_precision": "exact",
            "publish_date_text": None,
        }

    fetcher = client._channel_fetcher
    mocker.patch.object(
        fetcher,
        "_get_raw_channel_videos_generator",
        return_value=iter(
            [{k: v for k, v in i.items() if k != "_exact"} for i in raw_items]
        ),
    )
    fetcher.video_fetcher = MagicMock()
    fetcher.video_fetcher.get_video_metadata.side_effect = fake_meta
    return fetcher, hydrations


def test_published_between_returns_exact_window_with_log_hydrations(client, mocker):
    """The bisect funnel: 90 days of videos, 3-day target window in the
    middle → correct exact-date membership with O(log n) probe
    hydrations, NOT one hydration per video in the padded window."""
    raw = _daily_raw_items(90)
    fetcher, hydrations = _fetcher_for_bisect(client, mocker, raw)

    start = raw[46]["_exact"].date()   # 3-day window: items 44..46
    end = raw[44]["_exact"].date()
    result = list(
        client.get_videos_published_between(
            "https://www.youtube.com/@x", start_date=start, end_date=end
        )
    )

    assert [v["video_id"] for v in result] == ["vid0000044", "vid0000045", "vid0000046"]
    for v in result:
        assert v["publish_date_precision"] == "exact"
        assert start <= v["publish_date"].date() <= end
    # 2 bisects over 90 items ≈ 14 probes + window(3) + margin(≤6);
    # anything near 90 means the funnel degenerated to brute force.
    assert len(set(hydrations)) <= 30, f"hydrated {len(set(hydrations))} of 90"


def test_published_between_tolerates_local_disorder(client, mocker):
    """Channel listings aren't perfectly chronological (premieres,
    pinned items). Swapping adjacent items around the boundary must not
    lose an in-window video — the margin re-check covers local
    disorder."""
    raw = _daily_raw_items(60)
    raw[29], raw[30] = raw[30], raw[29]  # disorder at the window edge
    fetcher, hydrations = _fetcher_for_bisect(client, mocker, raw)

    # window = exact days of original items 28..30
    days = sorted(i["_exact"] for i in raw if i["video_id"] in
                  {"vid0000028", "vid0000029", "vid0000030"})
    result = list(
        client.get_videos_published_between(
            "https://www.youtube.com/@x",
            start_date=days[0].date(),
            end_date=days[-1].date(),
        )
    )
    assert {v["video_id"] for v in result} == {
        "vid0000028", "vid0000029", "vid0000030"
    }


def test_published_between_hour_bounds(client, mocker):
    """datetime bounds give an hour-window on exact dates — the
    original motivating query in one call."""
    raw = _daily_raw_items(30)
    fetcher, hydrations = _fetcher_for_bisect(client, mocker, raw)
    target = raw[10]["_exact"]  # published 08:00:29
    result = list(
        client.get_videos_published_between(
            "https://www.youtube.com/@x",
            start_date=target.replace(hour=7, minute=30),
            end_date=target.replace(hour=8, minute=30),
        )
    )
    assert [v["video_id"] for v in result] == ["vid0000010"]


def test_published_between_requires_start(client):
    with pytest.raises(ValueError, match="start_date"):
        list(client.get_videos_published_between("https://www.youtube.com/@x", start_date=None))
