import pytest

from yt_meta.filtering import apply_filters, partition_filters

# --- Unit Tests for apply_filters ---


@pytest.fixture
def sample_video():
    """A sample video metadata object for testing filters."""
    return {
        "video_id": "test_id_123",
        "title": "A Great Video",
        "view_count": 15000,
        "duration_seconds": 300,  # 5 minutes
    }


def test_view_count_gt_passes(sample_video):
    filters = {"view_count": {"gt": 10000}}
    assert apply_filters(sample_video, filters) is True


def test_view_count_gt_fails(sample_video):
    filters = {"view_count": {"gt": 20000}}
    assert apply_filters(sample_video, filters) is False


def test_view_count_lt_passes(sample_video):
    filters = {"view_count": {"lt": 20000}}
    assert apply_filters(sample_video, filters) is True


def test_view_count_lt_fails(sample_video):
    filters = {"view_count": {"lt": 10000}}
    assert apply_filters(sample_video, filters) is False


def test_view_count_eq_passes(sample_video):
    filters = {"view_count": {"eq": 15000}}
    assert apply_filters(sample_video, filters) is True


def test_view_count_eq_fails(sample_video):
    filters = {"view_count": {"eq": 10000}}
    assert apply_filters(sample_video, filters) is False


def test_no_view_count_fails(sample_video):
    filters = {"view_count": {"gt": 10000}}
    del sample_video["view_count"]
    assert apply_filters(sample_video, filters) is False


# --- Unit Tests for duration_seconds ---


def test_duration_gt_passes(sample_video):
    filters = {"duration_seconds": {"gt": 60}}
    assert apply_filters(sample_video, filters) is True


def test_duration_lt_fails(sample_video):
    filters = {"duration_seconds": {"lt": 60}}
    assert apply_filters(sample_video, filters) is False


def test_duration_multiple_conditions_pass(sample_video):
    filters = {"duration_seconds": {"gte": 300, "lte": 300}}
    assert apply_filters(sample_video, filters) is True


def test_no_duration_fails(sample_video):
    filters = {"duration_seconds": {"gt": 100}}
    del sample_video["duration_seconds"]
    assert apply_filters(sample_video, filters) is False


# --- Integration Test ---


def test_apply_filters_like_count():
    """Test filtering by like_count."""
    videos = [
        {"video_id": "1", "like_count": 50},
        {"video_id": "2", "like_count": 150},
        {"video_id": "3", "like_count": 100},
    ]
    filters = {"like_count": {"gte": 100}}
    filtered_videos = [v for v in videos if apply_filters(v, filters)]
    assert len(filtered_videos) == 2
    assert filtered_videos[0]["video_id"] == "2"
    assert filtered_videos[1]["video_id"] == "3"


def test_partition_filters_for_videos():
    """Test partitioning of filters for regular videos."""
    filters = {
        "view_count": {"gt": 1000},  # Fast
        "duration_seconds": {"lt": 300},  # Fast
        "like_count": {"gte": 100},  # Slow
        "title": {"contains": "Tutorial"},  # Now a fast filter for videos
    }
    fast, slow = partition_filters(filters, content_type="videos")
    assert "view_count" in fast
    assert "duration_seconds" in fast
    assert "like_count" in slow
    assert "title" in fast
    assert len(fast) == 3
    assert len(slow) == 1


def test_partition_filters_for_shorts():
    """Test partitioning of filters for shorts."""
    filters = {
        "view_count": {"gt": 1000},  # Fast
        "title": {"contains": "Funny"},  # Fast
        "duration_seconds": {"lt": 60},  # Slow
        "like_count": {"gte": 50},  # Slow
    }
    fast, slow = partition_filters(filters, content_type="shorts")
    assert "view_count" in fast
    assert "title" in fast
    assert "duration_seconds" in slow
    assert "like_count" in slow
    assert len(fast) == 2
    assert len(slow) == 2


def test_apply_filters_view_count():
    video = {"view_count": 1500}
    assert apply_filters(video, {"view_count": {"gt": 1000}})


def test_description_snippet_filter_rejected_full_description_works():
    """C1 (0.8.0): description_snippet was removed — only the retired
    videoRenderer shape emitted it, so the filter silently dropped every
    video on current lockup pages. It now fails validation loudly, and
    full_description (slow filter) covers the use case."""
    import pytest as _pytest

    from yt_meta.validators import validate_filters

    with _pytest.raises(ValueError, match="Unknown filter field"):
        validate_filters({"description_snippet": {"contains": "python"}})

    videos = [
        {"full_description": "A video about Python programming."},
        {"full_description": "A great video about cooking."},
        {"full_description": "A tutorial on pyTEst and other tools."},
    ]
    filters_py = {"full_description": {"contains": "python"}}
    filtered = [v for v in videos if apply_filters(v, filters_py)]
    assert len(filtered) == 1
    assert filtered[0]["full_description"] == "A video about Python programming."

    filters_re = {"full_description": {"re": r"pyt(hon|est)"}}
    filtered_re = [v for v in videos if apply_filters(v, filters_re)]
    assert len(filtered_re) == 2


def test_apply_filters_title():
    """Tests filtering by video title."""
    videos = [
        {"title": "An Introduction to Python"},
        {"title": "Advanced Python Programming"},
        {"title": "A video about Rust"},
    ]

    # Test 'contains'
    filters_py = {"title": {"contains": "python"}}
    filtered_py = [v for v in videos if apply_filters(v, filters_py)]
    assert len(filtered_py) == 2

    # Test 're'
    filters_re = {"title": {"re": r"^Advanced"}}
    filtered_re = [v for v in videos if apply_filters(v, filters_re)]
    assert len(filtered_re) == 1
    assert filtered_re[0]["title"] == "Advanced Python Programming"


def test_apply_filters_category():
    """Tests filtering by category."""
    videos = [
        {"category": "Science & Technology"},
        {"category": "Music"},
        {"category": "Gaming"},
        {"category": "DIY & Crafts"},
    ]
    filters = {"category": {"contains": "sci"}}
    filtered = [v for v in videos if apply_filters(v, filters)]
    assert len(filtered) == 1
    assert filtered[0]["category"] == "Science & Technology"

    filters_eq = {"category": {"eq": "Music"}}
    filtered_eq = [v for v in videos if apply_filters(v, filters_eq)]
    assert len(filtered_eq) == 1
    assert filtered_eq[0]["category"] == "Music"


def test_apply_filters_full_description():
    """Tests filtering by full_description."""
    videos = [
        {"full_description": "A deep dive into machine learning models."},
        {"full_description": "An unrelated video about baking."},
        {"full_description": "This tutorial covers deep neural networks."},
    ]
    filters = {"full_description": {"re": r"deep.*learning"}}
    filtered = [v for v in videos if apply_filters(v, filters)]
    assert len(filtered) == 1


def test_apply_filters_keywords():
    """Tests filtering by keywords."""
    videos = [
        {"keywords": ["python", "programming", "tutorial"]},
        {"keywords": ["cooking", "baking"]},
        {"keywords": ["rust", "systems", "programming"]},
    ]
    # Test 'contains' (any)
    filters_any = {"keywords": {"contains_any": ["python", "rust"]}}
    filtered_any = [v for v in videos if apply_filters(v, filters_any)]
    assert len(filtered_any) == 2

    # Test 'contains' (all)
    filters_all = {"keywords": {"contains_all": ["programming", "tutorial"]}}
    filtered_all = [v for v in videos if apply_filters(v, filters_all)]
    assert len(filtered_all) == 1
    assert filtered_all[0]["keywords"] == ["python", "programming", "tutorial"]


def test_l1_build_date_filter_from_kwargs_only():
    """L1: explicit start_date/end_date kwargs produce the canonical
    dict-shape publish_date filter ({"gte": ..., "lte": ...}). Returns
    the dates back too so callers can use them for short-circuit
    pagination.
    """
    from datetime import date

    from yt_meta.filtering import build_date_filter

    merged, start, end = build_date_filter(date(2023, 1, 1), date(2024, 12, 31))
    assert merged == {"publish_date": {"gte": date(2023, 1, 1), "lte": date(2024, 12, 31)}}
    assert start == date(2023, 1, 1)
    assert end == date(2024, 12, 31)


def test_l1_build_date_filter_extracts_bounds_from_existing_filter():
    """L1: when start_date/end_date kwargs are not given, the helper
    reads gt/gte (for start) and lt/lte (for end) from any existing
    publish_date entry in filters. This is the channel-fetcher
    behavior, now shared with playlist.
    """
    from datetime import date

    from yt_meta.filtering import build_date_filter

    existing = {"publish_date": {"gte": date(2023, 1, 1), "lt": date(2024, 12, 31)}}
    merged, start, end = build_date_filter(None, None, existing)
    assert start == date(2023, 1, 1)
    assert end == date(2024, 12, 31)


def test_l1_build_date_filter_kwargs_override_existing_filter():
    """L1: explicit kwargs win over values in the existing filter dict."""
    from datetime import date

    from yt_meta.filtering import build_date_filter

    existing = {"publish_date": {"gte": date(2020, 1, 1)}}
    merged, start, _ = build_date_filter(date(2024, 6, 1), None, existing)
    assert start == date(2024, 6, 1)
    assert merged["publish_date"]["gte"] == date(2024, 6, 1)


def test_l1_build_date_filter_converts_string_dates():
    """L1: string dates pass through parse_relative_date_string ('30d',
    'YYYY-MM-DD', 'January 1 2023', etc.). This was channel-side only;
    L1 makes it universal.
    """
    from datetime import date

    from yt_meta.filtering import build_date_filter

    _, start, end = build_date_filter("2023-01-01", "2024-12-31")
    assert isinstance(start, date)
    assert start.year == 2023 and start.month == 1 and start.day == 1
    assert end.year == 2024 and end.month == 12 and end.day == 31


def test_l1_build_date_filter_no_dates_returns_existing_filter_unchanged():
    """L1: when no dates are provided anywhere, the helper returns the
    filter dict unchanged and None for both bounds. Used as the no-op
    case by callers that always invoke the helper for uniformity.
    """
    from yt_meta.filtering import build_date_filter

    existing = {"view_count": {"gt": 1000}}
    merged, start, end = build_date_filter(None, None, existing)
    assert merged == {"view_count": {"gt": 1000}}
    assert start is None
    assert end is None


def test_m6_apply_filters_skips_video_with_missing_field_and_logs(caplog):
    """REGRESSION (M6): apply_filters treats a missing field
    (``video[key] is None``) as a filter failure — the video is
    silently dropped from the result. This is the right default for
    the common case ("give me videos with publish_date >= 2023" should
    not match videos with no publish_date), but it can surprise users
    debugging "why is this video missing from my results?".

    v0.6.0 keeps the behavior (skip-on-missing) and adds a DEBUG-level
    log when the drop happens so users can investigate. Documented in
    the apply_filters docstring and the README filter section.
    """
    import logging

    video = {"video_id": "dQw4w9WgXcQ", "title": "Test"}  # no publish_date
    filters = {"publish_date": {"gte": "2023-01-01"}}

    with caplog.at_level(logging.DEBUG, logger="yt_meta.filtering"):
        result = apply_filters(video, filters)

    assert result is False
    matching = [
        r for r in caplog.records
        if "publish_date" in r.message and r.levelno == logging.DEBUG
    ]
    assert matching, (
        "expected a DEBUG log mentioning the missing field; got "
        f"{[r.message for r in caplog.records]!r}"
    )


def test_apply_filters_publish_date():
    """Tests filtering by publish_date."""
    videos = [
        {"publish_date": "2023-01-15T12:00:00+00:00"},
        {"publish_date": "2023-08-01T10:00:00+00:00"},
        {"publish_date": "2022-12-25T18:00:00+00:00"},
    ]
    filters = {"publish_date": {"after": "2023-01-01"}}
    filtered = [v for v in videos if apply_filters(v, filters)]
    assert len(filtered) == 2

    filters_before = {"publish_date": {"before": "2023-01-01"}}
    filtered_before = [v for v in videos if apply_filters(v, filters_before)]
    assert len(filtered_before) == 1


# --- Integration Tests ---


def test_apply_filters_view_count_range():
    """Test a numerical range filter (e.g., gt and lt)."""
    video_in_range = {"view_count": 2000}
    video_out_of_range = {"view_count": 5000}
    filters = {"view_count": {"gt": 1000, "lt": 3000}}

    assert apply_filters(video_in_range, filters)
    assert not apply_filters(video_out_of_range, filters)


def test_c8_build_date_filter_normalizes_datetime_to_date():
    """REGRESSION (C8, 2026-07-05 review): only str inputs were
    normalized; a datetime passed as start_date/end_date flowed through
    to the channel generator's `video_publish_date.date() < final_start`
    comparison and raised TypeError (can't compare date and datetime)."""
    from datetime import date, datetime

    from yt_meta.filtering import build_date_filter

    merged, start, end = build_date_filter(
        datetime(2024, 6, 1, 12, 30), datetime(2024, 12, 31, 23, 59)
    )
    assert start == date(2024, 6, 1)
    assert type(start) is date
    assert end == date(2024, 12, 31)
    assert type(end) is date
    assert merged["publish_date"] == {"gte": date(2024, 6, 1), "lte": date(2024, 12, 31)}


def test_hour_bounds_compare_datetimes_on_exact_values():
    """REGRESSION (hour-truncation trap): _check_date_condition
    normalized both sides to calendar dates, so an hour-window filter
    was silently wrong — 'lt 12:00 same day' compared '5 July < 5 July'
    and dropped EVERYTHING, in-window or not. When the record is
    precision-exact and the bound carries time, compare full datetimes.
    Naive bounds against tz-aware values compare wall-clock (no
    TypeError)."""
    from datetime import datetime, timedelta, timezone

    tz = timezone(timedelta(hours=-7))
    morning = {
        "publish_date": datetime(2023, 7, 5, 8, 0, 29, tzinfo=tz),
        "publish_date_precision": "exact",
    }
    afternoon = {
        "publish_date": datetime(2023, 7, 5, 14, 0, 2, tzinfo=tz),
        "publish_date_precision": "exact",
    }
    window = {
        "publish_date": {
            "gte": datetime(2023, 7, 5, 8, 0),
            "lt": datetime(2023, 7, 5, 12, 0),
        }
    }
    assert apply_filters(morning, window) is True
    assert apply_filters(afternoon, window) is False


def test_hour_bounds_fall_back_to_dates_on_approximate_values():
    """A time-bearing bound against an APPROXIMATE value compares at
    date granularity — the time-of-day on an approximate value is
    query-time noise, not data."""
    from datetime import datetime

    video = {
        "publish_date": datetime(2023, 7, 5, 23, 45, 11),  # noise time
        "publish_date_precision": "approximate",
        "publish_date_text": "3 years ago",
    }
    assert apply_filters(
        video, {"publish_date": {"gte": datetime(2023, 7, 5, 8, 0)}}
    ) is True  # same calendar day passes despite 23:45 > nothing-meaningful


def test_bare_date_bounds_keep_calendar_semantics():
    """A bare date bound means 'that calendar day' — unchanged, even on
    exact values."""
    from datetime import date, datetime, timedelta, timezone

    video = {
        "publish_date": datetime(
            2023, 7, 5, 8, 0, tzinfo=timezone(timedelta(hours=-7))
        ),
        "publish_date_precision": "exact",
    }
    assert apply_filters(video, {"publish_date": {"eq": date(2023, 7, 5)}}) is True


def test_date_kwargs_clobbering_hour_bounds_raises():
    """REGRESSION (found in live validation): passing start_date/
    end_date kwargs TOGETHER with a time-bearing publish_date filter
    silently replaced the hour-level bounds with day-level kwargs —
    the hour window evaporated with no error. Day-level override
    (kwargs win) stays documented behavior; clobbering TIME bounds
    must fail loudly."""
    from datetime import date, datetime

    import pytest as _pytest

    from yt_meta.filtering import build_date_filter

    with _pytest.raises(ValueError, match="publish_date"):
        build_date_filter(
            date(2026, 7, 1),
            date(2026, 7, 3),
            {"publish_date": {"gte": datetime(2026, 7, 1, 7, 30)}},
        )
