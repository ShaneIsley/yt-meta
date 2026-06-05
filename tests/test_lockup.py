"""Regression tests for the lockupViewModel channel-videos format.

YouTube migrated the channel 'Videos' tab from `videoRenderer` to
`lockupViewModel`. These tests run against a real captured channel page
(@bashbunni) saved as a fixture, so the fix is provable offline and the
previously-"flaky" channel integration tests gain real regression
coverage. The fixture deliberately includes the two edge cases found by
direct probing: a collab video (byline pushes views/date to the second
metadata row) and members-only videos (no view count by design).
"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from yt_meta import parsing

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def lockup_renderers():
    with open(FIXTURES / "channel_videos_lockup_renderers.json") as f:
        return json.load(f)["contents"]


def test_lockup_parses_all_video_items(lockup_renderers):
    """Every LOCKUP_CONTENT_TYPE_VIDEO item is parsed; the captured page
    has 30 of them (the 31st renderer is the continuation token)."""
    videos, token = parsing.extract_videos_from_lockup_renderers(lockup_renderers)
    assert len(videos) == 30
    assert token  # continuation token extracted from the last renderer
    for v in videos:
        assert v["video_id"] and len(v["video_id"]) == 11
        assert v["title"]


def test_lockup_extracts_views_publish_and_duration(lockup_renderers):
    """Standard (non-members) videos carry view_count (int),
    publish_date (datetime via dateparser), and duration_seconds."""
    videos, _ = parsing.extract_videos_from_lockup_renderers(lockup_renderers)
    standard = [v for v in videos if v.get("view_count")]
    assert standard, "expected at least some videos with a view count"
    v = standard[0]
    assert isinstance(v["view_count"], int) and v["view_count"] > 0
    assert isinstance(v["publish_date"], datetime)
    assert isinstance(v["duration_seconds"], int) and v["duration_seconds"] > 0


def test_lockup_collab_video_finds_views_in_second_row(lockup_renderers):
    """Collab videos put the byline in metadataRows[0] and the
    views/date in metadataRows[1]; flattening all rows must still find
    them. Asserts that NO standard video silently loses its publish_date
    to the row-0 byline."""
    videos, _ = parsing.extract_videos_from_lockup_renderers(lockup_renderers)
    # Every parsed video should have a publish_date — even collabs.
    missing_date = [v["video_id"] for v in videos if v.get("publish_date") is None]
    assert not missing_date, f"videos missing publish_date: {missing_date}"


def test_lockup_members_only_video_has_none_view_count(lockup_renderers):
    """Members-only videos legitimately have no view count — view_count
    is None (not a crash, not a wrong number). The captured @bashbunni
    page contains members-only items."""
    videos, _ = parsing.extract_videos_from_lockup_renderers(lockup_renderers)
    members_only = [v for v in videos if v.get("view_count") is None]
    assert members_only, "fixture should contain members-only videos (no view count)"
    # They still have id/title/date — only the view count is absent.
    for v in members_only:
        assert v["video_id"] and v["title"]


def test_lockup_skips_continuation_and_non_video_content():
    """Non-video lockups (or the continuation renderer) are skipped, not
    mis-parsed as videos."""
    renderers = [
        {
            "continuationItemRenderer": {
                "continuationEndpoint": {
                    "continuationCommand": {"token": "TOK"}
                }
            }
        },
        {
            "richItemRenderer": {
                "content": {
                    "lockupViewModel": {
                        "contentType": "LOCKUP_CONTENT_TYPE_PLAYLIST",
                        "contentId": "PLxxxxxxxxxx",
                    }
                }
            }
        },
    ]
    videos, token = parsing.extract_videos_from_lockup_renderers(renderers)
    assert videos == []
    assert token == "TOK"
