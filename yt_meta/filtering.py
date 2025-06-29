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
FAST_FILTER_KEYS = {
    "view_count",
    "duration_seconds",
    "description_snippet",
    "title",
    "publish_date",
}

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


def partition_filters(filters: dict) -> tuple[dict, dict]:
    """Separates a filter dictionary into fast and slow filters."""
    if not filters:
        return {}, {}

    fast_filters = {k: v for k, v in filters.items() if k in FAST_FILTER_KEYS}
    slow_filters = {k: v for k, v in filters.items() if k in SLOW_FILTER_KEYS}

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


def _check_date_condition(video_value, condition_dict) -> bool:
    """
    Checks if a date video value meets all conditions in the dictionary.
    Supports gt, gte, lt, lte, eq, after, before.
    """
    for op, filter_value in condition_dict.items():
        # If the video value is a date, ensure the filter value is also a date
        if isinstance(video_value, date):
            if isinstance(filter_value, str):
                try:
                    filter_value = datetime.fromisoformat(filter_value).date()
                except ValueError:
                    try:
                        filter_value = datetime.strptime(
                            filter_value, "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        logger.warning(
                            "Invalid date format for filter value: %s", filter_value
                        )
                        return False

        # Standardize to date objects for comparison if one is a datetime and the other is a date
        comp_video_value = video_value
        if (
            isinstance(video_value, datetime)
            and isinstance(filter_value, date)
            and not isinstance(filter_value, datetime)
        ):
            comp_video_value = video_value.date()

        if op == "eq":
            if not comp_video_value == filter_value:
                return False
        elif op == "gt" or op == "after":
            if not comp_video_value > filter_value:
                return False
        elif op == "gte":
            if not comp_video_value >= filter_value:
                return False
        elif op == "lt" or op == "before":
            if not comp_video_value < filter_value:
                return False
        elif op == "lte":
            if not comp_video_value <= filter_value:
                return False
        else:  # Should be unreachable due to validator
            return False
    return True


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
        else: # Should be unreachable due to validator
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


def apply_filters(video: dict, filters: dict) -> bool:
    """
    Checks if a video dictionary passes a set of filters.

    Args:
        video: The video metadata dictionary.
        filters: The dictionary of filters to apply.

    Returns:
        True if the video passes all filters, False otherwise.
    """
    for key, condition in filters.items():
        if video.get(key) is None:
            return False  # If the key doesn't exist, it can't match

        schema_type = FILTER_SCHEMA[key]["schema_type"]
        video_value = video.get(key)

        passes = False
        if schema_type == "numerical":
            passes = _check_numerical_condition(video_value, condition)
        elif schema_type == "date":
            if isinstance(video_value, str):
                video_value = dateparser.parse(video_value, settings={'STRICT_PARSING': True})
            if video_value:
                passes = _check_date_condition(video_value, condition)
        elif schema_type == "text":
            passes = _check_text_condition(video_value, condition)
        elif schema_type == "list":
            passes = _check_list_condition(video_value, condition)
        elif schema_type == "bool":
            passes = _check_bool_condition(video_value, condition)

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

        video_value = comment.get(key)
        if video_value is None:
            return False

        if key in {"like_count", "reply_count"}:
            if not _check_numerical_condition(video_value, condition):
                return False
        elif key in {"text", "author", "channel_id"}:
            if not _check_text_condition(video_value, condition):
                return False
        elif key in {"is_reply", "is_hearted_by_owner", "is_by_owner"}:
            if not _check_boolean_condition(video_value, condition):
                return False
        elif key == "publish_date":
            if not _check_date_condition(video_value, condition):
                return False
    return True


def _check_boolean_condition(value: bool, condition_dict: dict) -> bool:
    """
    Checks if a boolean value meets the 'eq' condition.
    """
    op = next(iter(condition_dict))
    filter_value = condition_dict[op]

    if op != "eq":
        logger.warning("Unrecognized boolean operator: %s. Only 'eq' is supported.", op)
        return False
    
    return value == filter_value 