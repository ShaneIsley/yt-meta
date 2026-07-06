"""
This module contains the logic for advanced, dictionary-based filtering.

It defines which filters are "fast" (available on the initial page load) and
which are "slow" (requiring a separate request per video). The main entry
point is `apply_filters`, which checks if a given video dictionary meets a
set of specified criteria.
"""

import logging
import re
from datetime import date, datetime

import dateparser

from yt_meta.validators import FILTER_SCHEMA

logger = logging.getLogger(__name__)


# These keys are available in the basic video metadata from channel/playlist pages.
# C1/R2: this set must stay a subset of what parse_lockup_view_model
# emits (pinned by tests/test_filter_schema_contract.py).
# description_snippet was removed in 0.8.0 — only the retired
# videoRenderer shape carried it, so as a fast filter it silently
# dropped every video on current lockup-shaped pages. Use
# full_description (slow) instead.
FAST_VIDEO_FILTERS = {
    "view_count",
    "duration_seconds",
    "publish_date",
    "title",
}
FAST_SHORTS_FILTERS = {"view_count", "title"}

# These keys require fetching full metadata for each video, making them slower.
SLOW_FILTER_KEYS = {
    "like_count",
    "category",
    "keywords",
    "full_description",
}

# C1/R2: these are the names the comment parser actually emits (pinned
# by tests/test_filter_schema_contract.py). 0.8.0 renamed the three
# phantom keys that never matched anything: channel_id →
# author_channel_id, is_by_owner → is_creator, is_hearted_by_owner →
# is_hearted; is_pinned is newly filterable.
COMMENT_FILTER_KEYS = {
    "text",
    "author",
    "author_channel_id",
    "like_count",
    "reply_count",
    "publish_date",
    "is_reply",
    "is_hearted",
    "is_creator",
    "is_pinned",
}


def partition_filters(filters: dict, content_type: str) -> tuple[dict, dict]:
    """
    Partitions filters into fast and slow filters based on the content type.

    Fast filters can be applied to the basic metadata fetched in the initial channel/shorts page load.
    Slow filters require fetching full metadata for each individual video/short.

    Args:
        filters: The dictionary of filter conditions.
        content_type: The type of content, either 'videos' or 'shorts'.

    Returns:
        A tuple of (fast_filters, slow_filters).
    """
    if not filters:
        return {}, {}
    fast_filters = {}
    slow_filters = {}
    for key, value in filters.items():
        if content_type == "videos" and key in FAST_VIDEO_FILTERS:
            fast_filters[key] = value
        elif content_type == "shorts" and key in FAST_SHORTS_FILTERS:
            fast_filters[key] = value
        else:
            slow_filters[key] = value
    return fast_filters, slow_filters


def _check_numerical_condition(video_value, condition_dict) -> bool:
    """
    Checks if a numerical video value meets all conditions in the dictionary.
    Supports gt, gte, lt, lte, eq.
    """
    for op, filter_value in condition_dict.items():
        if op == "eq":
            if not video_value == filter_value:
                return False
        elif op == "gt":
            if not video_value > filter_value:
                return False
        elif op == "gte":
            if not video_value >= filter_value:
                return False
        elif op == "lt":
            if not video_value < filter_value:
                return False
        elif op == "lte":
            if not video_value <= filter_value:
                return False
        else:  # Should be unreachable due to validator
            return False
    return True


def _check_date_condition(video_value, filter_value, op, precision=None) -> bool:
    """
    Checks if a date video value meets a single condition.
    Supports gt, gte, lt, lte, eq, after, before.

    Granularity: when the filter bound is a ``datetime`` (the caller
    cares about time-of-day) AND the record's value is precision-exact,
    full datetimes are compared — a naive bound against a tz-aware
    value compares wall-clock. In every other case both sides are
    truncated to calendar dates: the time-of-day on an APPROXIMATE
    value is query-time noise, and a bare ``date`` bound means "that
    calendar day". (Previously hour bounds were ALWAYS truncated, which
    made a same-day hour window drop everything, silently.)
    """
    # Ensure both values are datetime objects before comparison
    if isinstance(video_value, str):
        video_value = dateparser.parse(
            video_value, settings={"PREFER_DATES_FROM": "past"}
        )
    if isinstance(filter_value, str):
        filter_value = dateparser.parse(
            filter_value, settings={"PREFER_DATES_FROM": "past"}
        )

    if not isinstance(video_value, datetime | date) or not isinstance(
        filter_value, datetime | date
    ):
        return False  # Cannot compare if parsing failed

    if (
        precision == "exact"
        and isinstance(filter_value, datetime)
        and isinstance(video_value, datetime)
    ):
        # Time-aware comparison. Mixed naive/aware compares wall-clock.
        v_aware = video_value.tzinfo is not None
        f_aware = filter_value.tzinfo is not None
        if v_aware != f_aware:
            video_value = video_value.replace(tzinfo=None)
            filter_value = filter_value.replace(tzinfo=None)
        comp_video_value, comp_filter_value = video_value, filter_value
    else:
        # Standardize to date objects for comparison
        comp_video_value = (
            video_value.date() if isinstance(video_value, datetime) else video_value
        )
        comp_filter_value = (
            filter_value.date() if isinstance(filter_value, datetime) else filter_value
        )

    if op == "eq":
        return comp_video_value == comp_filter_value
    if op in ("gt", "after"):
        return comp_video_value > comp_filter_value
    if op == "gte":
        return comp_video_value >= comp_filter_value
    if op in ("lt", "before"):
        return comp_video_value < comp_filter_value
    if op == "lte":
        return comp_video_value <= comp_filter_value

    return False  # Should be unreachable due to validator


def _check_text_condition(video_value, condition_dict) -> bool:
    """
    Checks if a text video value meets all conditions in the dictionary.
    Supports 'contains', 're', and 'eq'.
    """
    for op, filter_value in condition_dict.items():
        if op == "contains":
            if filter_value.lower() not in video_value.lower():
                return False
        elif op == "re":
            if not re.search(filter_value, video_value, re.IGNORECASE):
                return False
        elif op == "eq":
            if filter_value.lower() != video_value.lower():
                return False
        else:  # Should be unreachable due to validator
            return False
    return True


def _check_list_condition(video_value_list, condition_dict) -> bool:
    """
    Checks if a list of video values meets the conditions in the dictionary.
    Supports 'contains_any' and 'contains_all'.
    """
    # Ensure video_value_list is a list of lowercase strings for case-insensitive matching
    video_value_list = [str(v).lower() for v in video_value_list]

    contains_any = condition_dict.get("contains_any", [])
    if contains_any:
        # Ensure filter values are a list of lowercase strings
        filter_values = [str(v).lower() for v in contains_any]
        if not any(v in video_value_list for v in filter_values):
            return False

    contains_all = condition_dict.get("contains_all", [])
    if contains_all:
        # Ensure filter values are a list of lowercase strings
        filter_values = [str(v).lower() for v in contains_all]
        if not all(v in video_value_list for v in filter_values):
            return False

    return True


def build_date_filter(
    start_date,
    end_date,
    filters: dict | None = None,
):
    """Unify date-filter construction across the fetchers.

    Reads any existing ``publish_date`` entry from ``filters`` (gt/gte
    for start, lt/lte for end), merges with explicit start_date /
    end_date kwargs (kwargs win), converts string dates via
    ``parse_relative_date_string``, and returns a tuple:

        (merged_filters_dict, final_start_date, final_end_date)

    Callers use ``merged_filters_dict`` for downstream filtering and
    ``final_start_date`` / ``final_end_date`` for short-circuit
    pagination (e.g. ChannelFetcher's renderer-level early-stop).

    Before L1, ChannelFetcher had the rich merging logic inline at
    fetchers.py:437-456 and PlaylistFetcher had a simpler but
    differently-shaped version at fetchers.py:609-615. The disagreement
    is what allowed H1 (PlaylistFetcher built tuples) to ship — the
    two paths weren't unified. M5 (validate_filters ran before the
    rewrite) had the same root cause.
    """
    # Import here to avoid a circular import (filtering.py is imported
    # by date_utils.py — wait, the other way actually, but keep local
    # to make the dep direction explicit).
    from .date_utils import parse_relative_date_string

    if filters is None:
        filters = {}
    else:
        filters = dict(filters)  # shallow copy so we don't mutate the caller's dict

    existing_pd = filters.get("publish_date", {}) or {}
    start_from_filter = existing_pd.get("gt") or existing_pd.get("gte")
    end_from_filter = existing_pd.get("lt") or existing_pd.get("lte")

    final_start = start_date if start_date is not None else start_from_filter
    final_end = end_date if end_date is not None else end_from_filter

    # C8: normalize every accepted shape to a plain date. datetime must
    # be checked BEFORE the str branch's implicit date passthrough —
    # datetime is a date subclass, and leaving one through crashed the
    # channel generator's `publish_date.date() < final_start` comparison.
    if isinstance(final_start, str):
        final_start = parse_relative_date_string(final_start)
    elif isinstance(final_start, datetime):
        final_start = final_start.date()
    if isinstance(final_end, str):
        final_end = parse_relative_date_string(final_end)
    elif isinstance(final_end, datetime):
        final_end = final_end.date()

    date_conditions = {}
    if final_start is not None:
        date_conditions["gte"] = final_start
    if final_end is not None:
        date_conditions["lte"] = final_end
    if date_conditions:
        filters["publish_date"] = date_conditions

    return filters, final_start, final_end


def condition_has_time(condition: dict | None) -> bool:
    """True when any bound in a publish_date condition is a ``datetime``
    — i.e. the caller cares about time-of-day, which only exact
    (hydrated) dates can honor."""
    if not condition:
        return False
    return any(isinstance(v, datetime) for v in condition.values())


def passes_padded_date_window(video: dict, condition: dict) -> bool:
    """The padded coarse cut of the date funnel: does this video's
    APPROXIMATE date fall inside the condition's window widened by the
    date's own rounding error (from ``publish_date_text`` granularity)?

    Used pre-hydration when full metadata will be fetched anyway: a "3
    years ago" date can be ~6 months off, so near-boundary videos must
    survive to hydration, where the exact date decides. Videos with no
    approximate date pass (hydration supplies the field — M-e).
    """
    from .date_utils import approx_date_resolution

    video_value = video.get("publish_date")
    if video_value is None:
        return True
    if isinstance(video_value, datetime):
        video_value = video_value.date()
    pad = approx_date_resolution(video.get("publish_date_text"))

    for op, bound in condition.items():
        if isinstance(bound, str):
            from .date_utils import parse_relative_date_string

            bound = parse_relative_date_string(bound)
        if isinstance(bound, datetime):
            bound = bound.date()
        if not isinstance(bound, date):
            continue
        if op in ("gt", "gte", "after") and video_value < bound - pad:
            return False
        if op in ("lt", "lte", "before") and video_value > bound + pad:
            return False
        if op == "eq" and abs(video_value - bound) > pad:
            return False
    return True


def apply_filters(video: dict, filters: dict | None) -> bool:
    """
    Checks if a video dictionary passes a set of filters.

    Args:
        video: The video metadata dictionary.
        filters: The dictionary of filters to apply.

    Returns:
        True if the video passes all filters, False otherwise.

    Missing-field semantics (M6): if ``video[key]`` is ``None`` or the
    key is absent, the video is treated as failing the filter — it
    cannot match. This is the right default for the common case
    ("``publish_date >= 2023``" should not include videos with no
    publish_date), but it can surprise users debugging "where did my
    video go?". A DEBUG log is emitted on each drop so the cause is
    discoverable; enable ``logging.DEBUG`` on ``yt_meta.filtering`` to
    see them.
    """
    if filters is None:
        return True  # If no filters are provided, consider the video as passing

    for key, condition in filters.items():
        if video.get(key) is None:
            # M6: explicit "missing field == filter fail" semantic.
            # Log at DEBUG so users debugging "where did my video go?"
            # can find it without spamming INFO/WARNING for the common
            # case.
            logger.debug(
                "apply_filters: dropping video %s — filter field %r is "
                "missing or None on this video",
                video.get("video_id", "<no id>"),
                key,
            )
            return False  # If the key doesn't exist, it can't match

        schema_type = FILTER_SCHEMA[key]["schema_type"]
        video_value = video.get(key)

        passes = True  # Assume true and break on first failure
        if schema_type == "numerical":
            passes = _check_numerical_condition(video_value, condition)
        elif schema_type == "date":
            precision = (
                video.get("publish_date_precision") if key == "publish_date" else None
            )
            for op, condition_value in condition.items():
                if not _check_date_condition(
                    video_value, condition_value, op, precision=precision
                ):
                    passes = False
                    break
        elif schema_type == "text":
            passes = _check_text_condition(video_value, condition)
        elif schema_type == "list":
            passes = _check_list_condition(video_value, condition)
        elif schema_type == "bool":
            passes = _check_boolean_condition(video_value, condition)

        if not passes:
            return False

    return True


def apply_comment_filters(comment: dict, filters: dict) -> bool:
    """
    Checks if a comment object meets the criteria specified in the filters dict.

    Args:
        comment: A dictionary representing the comment's metadata.
        filters: A dictionary specifying the filter conditions.
            Example:
            {
                "like_count": {"gt": 100},
                "text": {"contains": "support"}
            }

    Returns:
        True if the comment passes all filters, False otherwise.
    """
    for key, condition in filters.items():
        if key not in COMMENT_FILTER_KEYS:
            logger.warning("Unrecognized comment filter key: %s", key)
            continue

        comment_value = comment.get(key)
        if comment_value is None:
            return False

        passes = True  # Assume true, break on first failure
        if key in {"like_count", "reply_count"}:
            passes = _check_numerical_condition(comment_value, condition)
        elif key in {"text", "author", "author_channel_id"}:
            passes = _check_text_condition(comment_value, condition)
        elif key in {"is_reply", "is_hearted", "is_creator", "is_pinned"}:
            passes = _check_boolean_condition(comment_value, condition)
        elif key == "publish_date":
            for op, condition_value in condition.items():
                if not _check_date_condition(comment_value, condition_value, op):
                    passes = False
                    break
        if not passes:
            return False
    return True


def _check_boolean_condition(value: bool, condition_dict: dict) -> bool:
    """
    Checks if a boolean value matches the specified condition.
    Supports 'eq'.
    """
    if "eq" in condition_dict:
        return value == condition_dict["eq"]
    return False
