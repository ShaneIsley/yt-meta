"""R2 vocabulary-contract tests (C1, 2026-07-05 review).

The C1 bug class: the filter layer advertised keys (`channel_id`,
`is_by_owner`, `is_hearted_by_owner`) that the parser never emits —
and missing-key ⇒ reject meant those filters silently dropped every
comment. Unit tests colluded by filtering synthetic dicts written in
the filter layer's vocabulary.

These tests pin the contract on REAL parser output from captured
fixtures: every advertised filter key must exist in the dicts the
production parser actually produces. Drift on either side fails here
first.
"""

import json
from pathlib import Path

import pytest

from yt_meta import parsing
from yt_meta.comment_parser import CommentParser
from yt_meta.filtering import (
    COMMENT_FILTER_KEYS,
    FAST_SHORTS_FILTERS,
    FAST_VIDEO_FILTERS,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def real_comments():
    """Real comments from a captured first-page response ('Me at the
    zoo', top sort — contains the pinned @jawed comment and 4 hearted
    comments)."""
    with open(FIXTURES / "comment_first_page_pinned.json") as f:
        response = json.load(f)
    comments = CommentParser().extract_complete_comments(response)
    assert comments, "fixture must produce comments"
    return comments


@pytest.fixture(scope="module")
def real_lockup_videos():
    """Real videos from captured channel-tab lockupViewModel renderers
    — the CURRENT channel/playlist item shape."""
    with open(FIXTURES / "channel_videos_lockup_renderers.json") as f:
        renderers = json.load(f)["contents"]
    videos, _ = parsing.extract_videos_from_lockup_renderers(renderers)
    assert videos, "fixture must produce videos"
    return videos


def test_c1_every_comment_filter_key_exists_in_real_parser_output(real_comments):
    """REGRESSION (C1/R2): every key in COMMENT_FILTER_KEYS must be
    present in every comment the production parser emits. The buggy
    vocabulary (channel_id/is_by_owner/is_hearted_by_owner) fails this
    immediately."""
    for comment in real_comments:
        missing = COMMENT_FILTER_KEYS - set(comment.keys())
        assert not missing, (
            f"filter keys {missing} not present in real parser output "
            f"(comment {comment.get('id')}) — filtering on them silently "
            f"drops every comment"
        )


def test_c1_every_fast_video_filter_key_exists_in_lockup_output(real_lockup_videos):
    """REGRESSION (C1/R2): every FAST_VIDEO_FILTERS key must exist in
    parse_lockup_view_model output — the current channel item shape.
    `description_snippet` (emitted only by the retired videoRenderer
    shape) fails this: as a fast filter it silently dropped every video
    on current pages."""
    for video in real_lockup_videos:
        missing = FAST_VIDEO_FILTERS - set(video.keys())
        assert not missing, (
            f"fast filter keys {missing} not present in lockup parser "
            f"output (video {video.get('video_id')})"
        )


def test_c1_every_fast_shorts_filter_key_exists_in_shorts_output():
    """R2: same contract for the shorts parser."""
    with open(FIXTURES / "channel_videos_lockup_renderers.json") as f:
        json.load(f)  # ensure fixture dir intact; shorts shape below
    # Shorts use extract_shorts_from_renderers over shortsLockupViewModel;
    # reuse the captured MrBeast shorts page.
    html = (FIXTURES / "mr_beast_shorts_page.html").read_text()
    initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
    tabs = initial_data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
    shorts_tab = next(
        t["tabRenderer"]
        for t in tabs
        if t.get("tabRenderer", {}).get("title") == "Shorts"
    )
    renderers = shorts_tab["content"]["richGridRenderer"]["contents"]
    shorts, _ = parsing.extract_shorts_from_renderers(renderers)
    assert shorts
    for short in shorts:
        missing = FAST_SHORTS_FILTERS - set(short.keys())
        assert not missing, f"fast shorts filter keys {missing} missing"
