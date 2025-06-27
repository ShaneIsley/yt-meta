"""
This example demonstrates the robust filter validation system in `yt-meta`.

When you provide a `filters` dictionary to methods like `get_channel_videos`
or `get_video_comments`, the library immediately checks it for correctness.
This prevents you from accidentally running a long, slow query with a typo
in a filter name or operator.

This script shows how the library raises specific, helpful errors for
different kinds of invalid filter inputs.
"""
from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@TED/videos"

# --- Example 1: Using a field that does not exist ---
try:
    print("--- Testing with a non-existent filter field ---")
    invalid_filters_1 = {
        "view_count": {"gt": 1_000_000},
        "non_existent_field": {"eq": "some_value"}  # This field is invalid
    }
    # This will raise a ValueError before any network request is made.
    next(client.get_channel_videos(channel_url, filters=invalid_filters_1))
except ValueError as e:
    print(f"Successfully caught expected error: {e}\n")


# --- Example 2: Using an invalid operator for a valid field ---
try:
    print("--- Testing with an invalid operator for a field ---")
    invalid_filters_2 = {
        "view_count": {"contains": "1,000"}  # 'contains' is not valid for numerical fields
    }
    # This will also raise a ValueError.
    next(client.get_channel_videos(channel_url, filters=invalid_filters_2))
except ValueError as e:
    print(f"Successfully caught expected error: {e}\n")


# --- Example 3: Using an invalid value type for an operator ---
try:
    print("--- Testing with an invalid value type ---")
    invalid_filters_3 = {
        "title": {"contains": 12345}  # `contains` expects a string, not an integer
    }
    # This will raise a TypeError.
    next(client.get_channel_videos(channel_url, filters=invalid_filters_3))
except TypeError as e:
    print(f"Successfully caught expected error: {e}\n")


print("Filter validation demonstration complete.") 