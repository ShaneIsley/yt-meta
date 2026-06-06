"""Live structural contract test — run deliberately, not in CI by default.

WHY THIS EXISTS
---------------
The library parses YouTube's undocumented internal JSON, whose shape
changes without notice. When the channel "Videos" tab migrated from
``videoRenderer`` to ``lockupViewModel``, ``get_channel_videos`` started
returning *nothing* — and because the old integration tests asserted
volatile values (``assert len(videos) == 3``), the structural break
looked identical to a transient network flake and was dismissed as
"flaky" for some time.

This test is the antidote. It hits live YouTube but asserts the
**structural contract** our parsers depend on:

  - required keys are present,
  - values have the expected *types*,
  - numeric values fall in sane *ranges* (not exact figures),
  - genuinely-permanent identifiers match (e.g. the first YouTube
    video's id/title/year).

It deliberately does NOT assert volatile data (exact view counts,
comment counts, today's upload list), so it fails ONLY when YouTube
actually changes the structure we rely on — the failure mode that
should page us, distinguished from the noise of changing data.

HOW TO RUN
----------
Excluded from the default run AND from ``-m integration``::

    pytest -m contract          # run it deliberately
    pytest -m contract -v       # see each capability

TARGETS (chosen for maximal permanence)
---------------------------------------
- ``jNQXAC9IVRw`` "Me at the zoo" — the first YouTube video (2005). It
  will not be deleted, has a stable title, an English transcript, and
  millions of comments. Used for video metadata / transcript / comments.
- ``@jawed`` (UC4QobU6STFB0P71PMvOGN5A) — the uploader of the above; a
  permanent channel whose single upload is that video. Used for channel
  metadata and the critical channel-videos (lockupViewModel) path.
- A long-standing public playlist and a shorts-heavy channel for those
  two capabilities (content is allowed to change; only the *shape* is
  asserted).

If a target is ever removed by YouTube, update the constant — a target
going away is not a library regression.
"""
from datetime import datetime

import pytest

pytestmark = pytest.mark.contract

# --- Permanent targets ---
ZOO_ID = "jNQXAC9IVRw"
ZOO_URL = f"https://www.youtube.com/watch?v={ZOO_ID}"
JAWED_URL = "https://www.youtube.com/@jawed"
JAWED_CHANNEL_ID = "UC4QobU6STFB0P71PMvOGN5A"
# Content may change; only structure is asserted for these two.
PLAYLIST_ID = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"  # Corey Schafer, long-standing
SHORTS_CHANNEL = "https://www.youtube.com/@MrBeast"

STRUCTURE_CHANGED = (
    "Returned no data from a known-good permanent target. This usually "
    "means YouTube changed the response structure our parser depends on "
    "(cf. the lockupViewModel migration) — NOT a transient flake. "
    "Investigate the parser before assuming it's the network."
)


@pytest.fixture(scope="module")
def client():
    """One shared client for the whole contract run (single session,
    minimal requests)."""
    from yt_meta import YtMeta

    c = YtMeta()
    yield c
    c.close()


def test_contract_video_metadata(client):
    """video metadata: stable identifiers + typed, in-range fields."""
    m = client.get_video_metadata(ZOO_URL)
    assert m is not None, STRUCTURE_CHANGED

    # Genuinely permanent — safe to pin.
    assert m["video_id"] == ZOO_ID
    assert m["title"] == "Me at the zoo"
    assert isinstance(m["publish_date"], datetime)
    assert m["publish_date"].year == 2005

    # Non-functional invariants — type + sane range, never exact value.
    assert isinstance(m["channel_name"], str) and m["channel_name"]
    assert isinstance(m["view_count"], int) and m["view_count"] > 100_000_000
    assert isinstance(m["duration_seconds"], int) and m["duration_seconds"] > 0
    assert isinstance(m["like_count"], int) and m["like_count"] >= 0
    assert isinstance(m["keywords"], list)
    assert isinstance(m["thumbnails"], list) and m["thumbnails"]


def test_contract_video_status_field(client):
    """video status: a playable video reports status='ok' with the
    lifecycle timestamps; a deleted one reports status='unavailable'
    with YouTube's reason instead of a junk dict."""
    ok = client.get_video_metadata(ZOO_URL)
    assert ok["status"] == "ok"
    assert ok["status_reason"] is None
    assert ok["status_checked_at"] and ok["status_changed_at"]

    gone = client.get_video_metadata("https://www.youtube.com/watch?v=aaaaaaaaaaa")
    assert gone["status"] == "unavailable"
    assert isinstance(gone["status_reason"], str) and gone["status_reason"]


def test_contract_transcript(client):
    """transcript: accepts a URL (M9) and yields typed snippets."""
    tx = client.get_video_transcript(ZOO_URL)
    assert tx, STRUCTURE_CHANGED
    snippet = tx[0]
    assert {"text", "start", "duration"} <= set(snippet)
    assert isinstance(snippet["text"], str) and snippet["text"]
    assert isinstance(snippet["start"], int | float)
    assert isinstance(snippet["duration"], int | float)


def test_contract_channel_metadata(client):
    """channel metadata: permanent title/id + description key present."""
    m = client.get_channel_metadata(JAWED_URL)
    assert m, STRUCTURE_CHANGED
    assert m["title"] == "jawed"
    assert m["channel_id"] == JAWED_CHANNEL_ID
    assert "description" in m


def test_contract_channel_videos_lockup(client):
    """channel videos — the critical path that silently broke. A real
    structural change here returns an empty list; assert we get content
    with the right shape, with a loud message if not."""
    videos = list(client.get_channel_videos(JAWED_URL, max_videos=1))
    assert videos, STRUCTURE_CHANGED

    v = videos[0]
    assert isinstance(v["video_id"], str) and len(v["video_id"]) == 11
    assert isinstance(v["title"], str) and v["title"]
    # @jawed's single permanent upload is "Me at the zoo".
    assert v["video_id"] == ZOO_ID
    # publish_date proves the lockup date-extraction path is intact.
    if v.get("publish_date") is not None:
        assert isinstance(v["publish_date"], datetime)


def test_contract_channel_videos_full_metadata(client):
    """channel videos with fetch_full_metadata=True — the enrichment
    path that merges per-video metadata (like_count, category, keywords)
    onto each renderer. A distinct code path from the basic listing."""
    videos = list(
        client.get_channel_videos(JAWED_URL, max_videos=1, fetch_full_metadata=True)
    )
    assert videos, STRUCTURE_CHANGED
    v = videos[0]
    # Fields that only appear after full-metadata enrichment.
    assert isinstance(v.get("like_count"), int)
    assert "category" in v
    assert isinstance(v.get("keywords"), list)


def test_contract_channel_shorts(client):
    """channel shorts: validates the shortsLockupViewModel parser shape.
    Content may change; require at least one with the right shape."""
    shorts = list(client.get_channel_shorts(SHORTS_CHANNEL, max_videos=1))
    assert shorts, STRUCTURE_CHANGED
    s = shorts[0]
    assert isinstance(s["video_id"], str) and len(s["video_id"]) == 11
    assert isinstance(s["title"], str) and s["title"]


def test_contract_playlist_videos(client):
    """playlist videos: validates playlistVideoRenderer shape (a separate
    path from channel videos — confirmed unaffected by the lockup change)."""
    videos = list(client.get_playlist_videos(PLAYLIST_ID, max_videos=1))
    assert videos, STRUCTURE_CHANGED
    v = videos[0]
    assert isinstance(v["video_id"], str) and len(v["video_id"]) == 11
    assert isinstance(v["title"], str) and v["title"]


def test_contract_comments(client):
    """comments: typed, required-key contract on the comment shape."""
    comments = list(client.get_video_comments(ZOO_URL, limit=5))
    assert comments, STRUCTURE_CHANGED
    c = comments[0]
    for key in ("id", "text", "author", "like_count", "reply_count", "is_reply"):
        assert key in c, f"comment missing key {key!r} — shape changed"
    assert isinstance(c["id"], str) and c["id"]
    assert isinstance(c["text"], str)
    assert isinstance(c["author"], str)
    assert isinstance(c["like_count"], int)
    assert isinstance(c["reply_count"], int)
    assert isinstance(c["is_reply"], bool)


def test_contract_comment_filters(client):
    """comment filters (M19): the filter pipeline runs against live data
    and every returned comment satisfies the predicate."""
    comments = list(
        client.get_video_comments(
            ZOO_URL, limit=20, filters={"like_count": {"gte": 1}}
        )
    )
    # Don't require a specific count (volatile) — assert the predicate
    # holds on whatever passed the filter.
    for c in comments:
        assert c["like_count"] >= 1


def test_contract_reply_tokens_and_replies(client):
    """reply-token path: with_reply_tokens must surface continuation
    tokens for comments that have replies, and get_comment_replies must
    resolve them to actual reply comments.

    This asserts token PRESENCE structurally (not skip-on-missing): the
    top comments on "Me at the zoo" reliably have hundreds of replies,
    so zero surfaced tokens means the reply-continuation extraction
    broke — which is exactly what happened when YouTube moved the token
    from commentRepliesRenderer.contents[] to .subThreads[]. A contract
    test that skipped here would have missed it."""
    top = list(
        client.get_video_comments_with_reply_tokens(
            ZOO_URL, sort_by="top", limit=20
        )
    )
    assert top, STRUCTURE_CHANGED

    have_replies = [c for c in top if c.get("reply_count", 0) > 0]
    assert have_replies, (
        "no top comment reported replies — unexpected for this video; "
        "comment shape may have changed"
    )
    tokened = [c for c in top if c.get("reply_continuation_token")]
    assert tokened, (
        f"{len(have_replies)} top comments have replies but NONE surfaced a "
        f"reply_continuation_token — the reply-continuation extraction is "
        f"broken (cf. the contents[] -> subThreads[] migration). " + STRUCTURE_CHANGED
    )

    token = tokened[0]["reply_continuation_token"]
    assert isinstance(token, str) and len(token) > 10
    replies = list(
        client.get_comment_replies(ZOO_URL, reply_continuation_token=token, limit=2)
    )
    assert replies, "reply token did not resolve to any replies — reply fetch broke"
    r = replies[0]
    assert isinstance(r["text"], str)
    assert isinstance(r["author"], str) and r["author"]
