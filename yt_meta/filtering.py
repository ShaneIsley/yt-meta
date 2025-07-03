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
FAST_VIDEO_FILTERS = {
    "view_count",
    "duration_seconds",
    "publish_date",
    "title",
    "description_snippet",
}
FAST_SHORTS_FILTERS = {"view_count", "title"}

# These keys require fetching full metadata for each video, making them slower.
SLOW_FILTER_KEYS = {
    "like_count",
    "category",
    "keywords",
    "full_description",
}

COMMENT_FILTER_KEYS = {
    "text",
    "author",
    "like_count",
    "reply_count",
    "publish_date",
    "is_reply",
    "is_hearted_by_owner",
    "is_by_owner",
    "channel_id",
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


def _check_date_condition(video_value, filter_value, op) -> bool:
    """
    Checks if a date video value meets a single condition.
    Supports gt, gte, lt, lte, eq, after, before.
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


def apply_filters(video: dict, filters: dict | None) -> bool:
    """
    Checks if a video dictionary passes a set of filters.

    Args:
        video: The video metadata dictionary.
        filters: The dictionary of filters to apply.

    Returns:
        True if the video passes all filters, False otherwise.
    """
    if filters is None:
        return True  # If no filters are provided, consider the video as passing

    for key, condition in filters.items():
        if video.get(key) is None:
            return False  # If the key doesn't exist, it can't match

        schema_type = FILTER_SCHEMA[key]["schema_type"]
        video_value = video.get(key)

        passes = True  # Assume true and break on first failure
        if schema_type == "numerical":
            passes = _check_numerical_condition(video_value, condition)
        elif schema_type == "date":
            for op, condition_value in condition.items():
                if not _check_date_condition(video_value, condition_value, op):
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
        elif key in {"text", "author", "channel_id"}:
            passes = _check_text_condition(comment_value, condition)
        elif key in {"is_reply", "is_hearted_by_owner", "is_by_owner"}:
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
