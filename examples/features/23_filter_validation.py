"""
Example: Filter validation

Methods that take a `filters` dict, such as `get_channel_videos` and
`get_video_comments`, check it when you call them, before any request is made.
A typo in a field name or operator raises right away instead of after a long
fetch. This script triggers three of those errors.
"""

from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@TED/videos"

try:
    print("Unknown filter field")
    invalid_filters_1 = {
        "view_count": {"gt": 1_000_000},
        "non_existent_field": {"eq": "some_value"},
    }
    # Raises ValueError on the call, before any network request.
    next(client.get_channel_videos(channel_url, filters=invalid_filters_1))
except ValueError as e:
    print(f"Caught expected error: {e}\n")


try:
    print("Invalid operator for a field")
    invalid_filters_2 = {
        "view_count": {
            "contains": "1,000"
        }  # 'contains' is not valid for numeric fields
    }
    next(client.get_channel_videos(channel_url, filters=invalid_filters_2))
except ValueError as e:
    print(f"Caught expected error: {e}\n")


try:
    print("Wrong value type")
    invalid_filters_3 = {
        "title": {"contains": 12345}  # `contains` expects a string
    }
    # A wrong value type raises TypeError rather than ValueError.
    next(client.get_channel_videos(channel_url, filters=invalid_filters_3))
except TypeError as e:
    print(f"Caught expected error: {e}\n")


print("Done.")
