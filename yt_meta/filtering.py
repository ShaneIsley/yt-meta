import logging
import re

logger = logging.getLogger(__name__)


# These keys are available in the basic video metadata from channel/playlist pages.
FAST_FILTER_KEYS = {"view_count", "duration_seconds"}

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


def _check_condition(video_value, condition_dict) -> bool:
    """Checks if a video value meets the conditions in the dictionary."""
    for op, filter_value in condition_dict.items():
        if op == "gt" and not video_value > filter_value:
            return False
        if op == "gte" and not video_value >= filter_value:
            return False
        if op == "lt" and not video_value < filter_value:
            return False
        if op == "lte" and not video_value <= filter_value:
            return False
        if op == "eq" and not video_value == filter_value:
            return False
    return True


def apply_filters(video: dict, filters: dict) -> bool:
    """
    Checks if a video object meets the criteria specified in the filters dict.

    Returns:
        True if the video passes all filters, False otherwise.
    """
    for key, condition in filters.items():
        if key == "view_count":
            # The view count key is different in basic vs. full metadata.
            # 'viewCount' (basic) or 'view_count' (full).
            video_value = video.get("view_count") or video.get("viewCount")
            if video_value is None:
                return False  # Cannot filter if the value doesn't exist

            if not _check_condition(video_value, condition):
                return False
        
        elif key == "duration_seconds":
            # The duration key is different in basic vs. full metadata.
            # 'lengthSeconds' (basic) or 'duration_seconds' (full).
            video_value = video.get("duration_seconds") or video.get("lengthSeconds")
            if video_value is None:
                return False # Cannot filter if the value doesn't exist
            
            if not _check_condition(video_value, condition):
                return False

        elif key == "like_count":
            # like_count is only available in full metadata
            video_value = video.get("like_count")
            if video_value is None:
                return False  # Cannot filter if the value doesn't exist

            if not _check_condition(video_value, condition):
                return False

    return True 