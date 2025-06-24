"""
This module contains the logic for advanced, dictionary-based filtering.

It defines which filters are "fast" (available on the initial page load) and
which are "slow" (requiring a separate request per video). The main entry
point is `apply_filters`, which checks if a given video dictionary meets a
set of specified criteria.
"""
import logging
import re

logger = logging.getLogger(__name__)


# These keys are available in the basic video metadata from channel/playlist pages.
FAST_FILTER_KEYS = {"view_count", "duration_seconds", "description_snippet", "title"}

# These keys require fetching full metadata for each video, making them slower.
SLOW_FILTER_KEYS = {"like_count"}


def partition_filters(filters: dict) -> tuple[dict, dict]:
    """Separates a filter dictionary into fast and slow filters."""
    if not filters:
        return {}, {}

    fast_filters = {k: v for k, v in filters.items() if k in FAST_FILTER_KEYS}
    slow_filters = {k: v for k, v in filters.items() if k in SLOW_FILTER_KEYS}

    # Log a warning for any unrecognized filter keys
    unrecognized_keys = filters.keys() - FAST_FILTER_KEYS - SLOW_FILTER_KEYS
    if unrecognized_keys:
        logger.warning("Unrecognized filter keys: %s", unrecognized_keys)

    return fast_filters, slow_filters


def _check_numerical_condition(video_value, condition_dict) -> bool:
    """
    Checks if a numerical video value meets the conditions in the dictionary.
    Supports gt, gte, lt, lte, eq.
    """
    for op, filter_value in condition_dict.items():
        if op == "gt" and not video_value > filter_value:
            return False
        elif op == "gte" and not video_value >= filter_value:
            return False
        elif op == "lt" and not video_value < filter_value:
            return False
        elif op == "lte" and not video_value <= filter_value:
            return False
        elif op == "eq" and not video_value == filter_value:
            return False
        elif op not in {"gt", "gte", "lt", "lte", "eq"}:
            logger.warning("Unrecognized operator: %s", op)
    return True


def _check_text_condition(video_value, condition_dict) -> bool:
    """
    Checks if a text video value meets the conditions in the dictionary.
    Supports 'contains' and 're'.
    """
    contains = condition_dict.get("contains")
    if contains is not None and contains.lower() not in video_value.lower():
        return False

    regex = condition_dict.get("re")
    if regex is not None and not re.search(regex, video_value, re.IGNORECASE):
        return False

    return True


def apply_filters(video: dict, filters: dict) -> bool:
    """
    Checks if a video object meets the criteria specified in the filters dict.

    Args:
        video: A dictionary representing the video's metadata.
        filters: A dictionary specifying the filter conditions.
            Example:
            {
                "view_count": {"gt": 1000},
                "title": {"contains": "Python"}
            }

    Returns:
        True if the video passes all filters, False otherwise.
    """
    for key, condition in filters.items():
        if key == "view_count":
            # Note: The key is 'viewCount' in basic metadata, 'view_count' in full.
            video_value = video.get("view_count") or video.get("viewCount")
            if video_value is None:
                return False  # Cannot filter if the value doesn't exist

            if not _check_numerical_condition(video_value, condition):
                return False

        elif key == "duration_seconds":
            # Note: The key is 'lengthSeconds' in basic metadata, 'duration_seconds' in full.
            video_value = video.get("duration_seconds") or video.get("lengthSeconds")
            if video_value is None:
                return False

            if not _check_numerical_condition(video_value, condition):
                return False

        elif key == "title":
            video_value = video.get("title")
            if video_value is None:
                return False

            if not _check_text_condition(video_value, condition):
                return False

        elif key == "description_snippet":
            video_value = video.get("descriptionSnippet")
            if video_value is None:
                return False

            if not _check_text_condition(video_value, condition):
                return False

        elif key == "like_count":
            # This key is only available in full metadata.
            video_value = video.get("like_count")
            if video_value is None:
                return False

            if not _check_numerical_condition(video_value, condition):
                return False

    return True 