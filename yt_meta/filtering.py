"""
This module contains the logic for advanced, dictionary-based filtering.

It defines which filters are "fast" (available on the initial page load) and
which are "slow" (requiring a separate request per video). The main entry
point is `apply_filters`, which checks if a given video dictionary meets a
set of specified criteria.
"""
import logging
import re
from datetime import date, datetime, timedelta

from .date_utils import parse_relative_date_string

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
        # If the video value is a date, ensure the filter value is also a date
        if isinstance(video_value, date):
            if isinstance(filter_value, str):
                try:
                    filter_value = datetime.fromisoformat(filter_value).date()
                except ValueError:
                    try:
                        filter_value = datetime.strptime(filter_value, "%Y-%m-%d").date()
                    except ValueError:
                        logger.warning("Invalid date format for filter value: %s", filter_value)
                        return False

        if op == "eq":
            return video_value == filter_value
        elif op == "gt" and not video_value > filter_value:
            return False
        elif op == "gte" and not video_value >= filter_value:
            return False
        elif op == "lt" and not video_value < filter_value:
            return False
        elif op == "lte" and not video_value <= filter_value:
            return False
        elif op not in {"gt", "gte", "lt", "lte", "eq"}:
            logger.warning("Unrecognized operator: %s", op)
    return True


def _check_text_condition(video_value, condition_dict) -> bool:
    """
    Checks if a text video value meets the conditions in the dictionary.
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
        elif op not in {"contains", "re", "eq"}:
            logger.warning("Unrecognized text operator: %s", op)
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
            video_value = video.get("view_count")
            if video_value is None:
                return False  # Cannot filter if the value doesn't exist

            if not _check_numerical_condition(video_value, condition):
                return False

        elif key == "duration_seconds":
            video_value = video.get("duration_seconds")
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
            video_value = video.get("description_snippet")
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

        elif key == "category":
            video_value = video.get("category")
            if video_value is None:
                return False
            if not _check_text_condition(video_value, condition):
                return False

        elif key == "full_description":
            video_value = video.get("full_description")
            if video_value is None:
                return False
            if not _check_text_condition(video_value, condition):
                return False

        elif key == "keywords":
            video_value = video.get("keywords")
            if not isinstance(video_value, list):
                return False
            if not _check_list_condition(video_value, condition):
                return False

        elif key == "publish_date":
            video_value_str = video.get("publish_date")
            if not video_value_str:
                # If there's no precise date, we cannot apply a precise filter.
                # The client should handle preliminary checks on 'publishedTimeText'.
                return False

            try:
                video_date = datetime.fromisoformat(video_value_str).date()
                if not _check_numerical_condition(video_date, condition):
                    return False
            except (ValueError, TypeError):
                logger.warning("Could not parse precise publish_date: %s", video_value_str)
                return False # Fail if the date is malformed

    return True 