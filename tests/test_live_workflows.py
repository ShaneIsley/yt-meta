"""Live, value-asserting checks for the workflow helpers and playlist
metadata, which the contract suite only shape-checks or skips.

HOW TO RUN
----------
Carries the ``contract`` marker, so it is excluded from the default run::

    uv run pytest -m contract tests/test_live_workflows.py -v

TARGETS
-------
Deliberately ordinary, not famous: a mid-size channel that uploads about
weekly (tens of thousands of views per video), one of its videos with a
few dozen comments, and one of its short playlists. Viral targets (Me at
the zoo, MrBeast) behave differently: comment volume, ranking, reply
truncation. They hide bugs that ordinary videos hit.

If a target disappears, swap in a similar one; that is not a regression.
"""

from datetime import datetime

import pytest

from yt_meta import YtMeta

pytestmark = pytest.mark.contract

CHANNEL = "https://www.youtube.com/@ArjanCodes"  # ~weekly uploads, 15-70k views
VIDEO_ID = "UEqk0njCuQo"  # ordinary upload: ~25 top-level comments, some threads
PLAYLIST_ID = "PLC0nd42SBTaPw_Ts4K5LYBLH1ymIAhux3"  # "Packages", ~9 videos


@pytest.fixture
def yt():
    client = YtMeta(accept_cookies=True)
    yield client
    client.close()


def _day(value):
    return value.date() if isinstance(value, datetime) else value


# --- get_playlist_metadata ----------------------------------------------


def test_playlist_metadata_matches_its_listing(yt):
    meta = yt.get_playlist_metadata(PLAYLIST_ID)
    videos = list(yt.get_playlist_videos(PLAYLIST_ID))

    assert meta["playlist_id"] == PLAYLIST_ID
    assert isinstance(meta["title"], str) and meta["title"]
    assert meta["author"] == "ArjanCodes"
    assert isinstance(meta["video_count"], int) and meta["video_count"] > 0
    assert meta["video_count"] == len(videos)
    assert len({v["video_id"] for v in videos}) == len(videos)


# --- iter_new_videos ----------------------------------------------------


def test_iter_new_videos_yields_only_videos_newer_than_marker(yt):
    newest = [v["video_id"] for v in yt.get_channel_videos(CHANNEL, max_videos=5)]
    assert len(newest) == 5
    marker = newest[3]

    new = [v["video_id"] for v in yt.iter_new_videos(CHANNEL, since_video_id=marker)]

    assert new == newest[:3], "must yield exactly the videos above the marker"


def test_iter_new_videos_with_newest_marker_yields_nothing(yt):
    newest = next(yt.get_channel_videos(CHANNEL, max_videos=1))["video_id"]
    assert list(yt.iter_new_videos(CHANNEL, since_video_id=newest)) == []


# --- get_videos_published_between ---------------------------------------


def test_published_between_matches_brute_force_exact_dates(yt):
    """Ground truth comes from hydrating a run of consecutive uploads by
    hand. The window is cut from the middle of that run, and both ends of
    the run must fall outside it, so every in-window video is in the run."""
    listing = list(yt.get_channel_videos(CHANNEL, max_videos=12))
    assert len(listing) == 12
    exact = {}
    for v in listing[2:12]:
        meta = yt.get_video_metadata(v["video_id"])
        assert meta["publish_date_precision"] == "exact"
        exact[v["video_id"]] = meta["publish_date"]

    run = listing[2:12]
    start = _day(exact[run[6]["video_id"]])
    end = _day(exact[run[3]["video_id"]])
    expected = {vid for vid, d in exact.items() if start <= _day(d) <= end}
    outer = (run[0]["video_id"], run[-1]["video_id"])
    if any(vid in expected for vid in outer) or start == end:
        pytest.skip("uploads too close together to cut a clean window today")

    result = list(
        yt.get_videos_published_between(CHANNEL, start_date=start, end_date=end)
    )

    assert {v["video_id"] for v in result} == expected
    for v in result:
        assert v["publish_date_precision"] == "exact"
        assert start <= _day(v["publish_date"]) <= end


# --- get_comment_threads ------------------------------------------------


def test_comment_threads_attach_replies_to_their_threads(yt):
    threads = list(yt.get_comment_threads(VIDEO_ID, limit=25, replies_per_thread=2))
    assert threads, "no comments returned"

    top_ids = [c["id"] for c, _ in threads]
    assert len(set(top_ids)) == len(top_ids)
    with_replies = 0
    for comment, replies in threads:
        assert comment["is_reply"] is False
        # YouTube can report more replies than it serves (held or removed
        # replies), so the count bounds the result from above only.
        assert len(replies) <= min(comment["reply_count"], 2)
        if comment["reply_count"]:
            assert replies, f"thread {comment['id']} has replies but none came back"
            with_replies += 1
        for reply in replies:
            assert reply["is_reply"] is True
            assert reply["id"] not in top_ids
            # Reply ids extend their parent's id: "<parent>.<suffix>".
            assert reply["id"].startswith(comment["id"] + ".")
    if not with_replies:
        pytest.skip("no comment on the target currently has replies")


def test_comment_threads_zero_replies_per_thread_skips_reply_requests(yt):
    api = yt.comment_fetcher.api_client
    calls = {"n": 0}
    original = api.make_reply_request

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    api.make_reply_request = counting
    threads = list(yt.get_comment_threads(VIDEO_ID, limit=10, replies_per_thread=0))

    assert threads
    assert all(replies == [] for _, replies in threads)
    assert calls["n"] == 0
