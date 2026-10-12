"""Live checks for the 2026-10 review fixes — run deliberately.

Each test exercises one fix against real YouTube through the public
``YtMeta`` API. Where the old bug was "keeps paginating", a request
counter with a hard cap turns a runaway into a fast, clear failure
instead of a test that never ends.

HOW TO RUN
----------
Carries the ``contract`` marker, so it is excluded from the default run::

    uv run pytest -m contract tests/test_live_fixes.py -v

Targets reuse the permanent ones from ``test_live_contract.py``.
Volatile data (which comments exist right now) is handled by skipping,
not failing, when the precondition is absent.
"""

import re
from datetime import date, datetime, timedelta

import pytest

from yt_meta import YtMeta

pytestmark = pytest.mark.contract

ZOO_ID = "jNQXAC9IVRw"  # "Me at the zoo": ~50 new comments an hour
JAWED_URL = "https://www.youtube.com/@jawed"  # one upload: Me at the zoo
VERITASIUM_URL = "https://www.youtube.com/@veritasium"  # hundreds of uploads
PLAYLIST_ID = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"  # Corey Schafer tutorials

REQUEST_CAP = 25


@pytest.fixture
def yt():
    client = YtMeta(accept_cookies=True)
    yield client
    client.close()


def _count_calls(obj, name, cap):
    """Wrap obj.name so calls are counted and the cap-th+1 call fails."""
    original = getattr(obj, name)
    calls = {"n": 0}

    def wrapper(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > cap:
            raise AssertionError(f"{name} called more than {cap} times")
        return original(*args, **kwargs)

    setattr(obj, name, wrapper)
    return calls


# --- Fix 1: relative date parsing -------------------------------------


def test_fresh_comments_are_dated_today_not_months_ago(yt):
    """"5 minutes ago" used to parse as 5 MONTHS ago. Every comment whose
    text is seconds/minutes/hours old must be dated within the last day."""
    comments = list(yt.get_video_comments(ZOO_ID, limit=40, sort_by="recent"))
    assert comments, "no comments returned"
    fresh = [
        c
        for c in comments
        if re.search(r"\b(second|minute|hour)s?\b", c.get("publish_date_text") or "")
    ]
    if not fresh:
        pytest.skip("no sub-day comments on the first page right now")
    floor = date.today() - timedelta(days=1)
    wrong = [
        (c["publish_date_text"], c["publish_date"])
        for c in fresh
        if c["publish_date"] is None or c["publish_date"] < floor
    ]
    assert not wrong, f"fresh comments misdated: {wrong}"


# --- Fix 2: since_date short-circuits comment pagination ----------------


def test_since_date_stops_comment_pagination(yt):
    """limit=None + since_date used to walk the entire comment stream.

    The cutoff comes from live data: a quiet video (an old tutorial) whose
    first two pages span more than one day, cut between the newest and
    oldest dates seen. The fetch must then end within those pages plus one,
    and leading pinned comments (often years old) must not end it early."""
    quiet = next(yt.get_playlist_videos(PLAYLIST_ID, max_videos=1))["video_id"]
    sample = list(yt.get_video_comments(quiet, limit=40, sort_by="recent"))
    days = sorted(
        {c["publish_date"] for c in sample if c["publish_date"] and not c["is_pinned"]}
    )
    if len(days) < 2:
        pytest.skip("first two pages of comments fall on a single day")
    cutoff = days[-1]  # the newest day: everything older must end the fetch

    calls = _count_calls(yt.comment_fetcher.api_client, "make_api_request", 3)
    comments = list(
        yt.get_video_comments(quiet, limit=None, since_date=cutoff, sort_by="recent")
    )

    assert comments, "nothing on or after the newest sampled day"
    assert all(c["publish_date"] >= cutoff for c in comments if not c["is_pinned"])
    print(f"\n  {len(comments)} comments since {cutoff} in {calls['n']} request(s)")


# --- Fix 3: publish_date filters keep their operators -------------------


def test_gt_on_exact_publish_day_excludes_that_video(yt):
    """gt used to be rewritten to gte, so the boundary-day video leaked in."""
    exact = yt.get_video_metadata(ZOO_ID)["publish_date"]
    day = exact.date() if isinstance(exact, datetime) else exact

    def ids(cond):
        return [
            v["video_id"]
            for v in yt.get_channel_videos(
                JAWED_URL, fetch_full_metadata=True, filters={"publish_date": cond}
            )
        ]

    assert ZOO_ID in ids({"gte": day})
    assert ZOO_ID not in ids({"gt": day})


def test_hour_level_bound_without_full_metadata_raises(yt):
    """datetime bounds used to be truncated to dates, so this documented
    ValueError never fired through the public API."""
    with pytest.raises(ValueError, match="fetch_full_metadata"):
        list(
            yt.get_channel_videos(
                JAWED_URL, filters={"publish_date": {"gte": datetime(2005, 4, 23, 12)}}
            )
        )


# --- Fix 4: stop_at_video_id stops even when the marker is filtered -----


def test_stop_at_filtered_out_marker_stops_pagination(yt):
    """The stop check used to run only after a yield; a filtered-out
    marker let pagination run through the whole channel."""
    first = list(yt.get_channel_videos(VERITASIUM_URL, max_videos=3))
    assert len(first) == 3, "need three uploads to pick a marker"
    marker = first[2]["video_id"]

    calls = _count_calls(yt._channel_fetcher, "_get_continuation_data", 3)
    result = list(
        yt.get_channel_videos(
            VERITASIUM_URL,
            stop_at_video_id=marker,
            filters={"title": {"contains": "zz-no-title-has-this-zz"}},
        )
    )

    assert result == []
    assert calls["n"] == 0, "paginated past the marker on the first page"


# --- Fix 5: trailing slash on channel tab URLs --------------------------


@pytest.mark.parametrize("suffix", ["/videos/", "/videos", "/"])
def test_trailing_slash_channel_url_returns_videos(yt, suffix):
    """".../videos/" used to become ".../videos/videos". YouTube happens
    to serve that URL too, so this guards the normalized form rather than
    reproducing a live failure (the old code also passes it)."""
    videos = list(yt.get_channel_videos(JAWED_URL + suffix, max_videos=1))
    assert [v["video_id"] for v in videos] == [ZOO_ID]


# --- Fix 6: clear_cache empties the SQLite cache ------------------------


def test_clear_cache_removes_expired_entries(tmp_path):
    """clear() used to stop at the first expired row."""
    with YtMeta(cache_path=str(tmp_path / "cache.db")) as yt:
        yt.get_video_metadata(ZOO_ID)
        list(yt.get_channel_videos(JAWED_URL, max_videos=1))
        assert len(yt.cache) >= 2
        yt.cache._conn.execute(
            # Expire the row clear() visits first (keys iterate in key
            # order): the old popitem() loop hit its KeyError and quit
            # with every other row still in place.
            "UPDATE cache SET timestamp = 0 WHERE key = (SELECT MIN(key) FROM cache)"
        )
        yt.cache._conn.commit()

        yt.clear_cache()

        assert len(yt.cache) == 0
