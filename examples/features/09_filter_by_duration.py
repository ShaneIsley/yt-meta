import itertools
import logging

from yt_meta import YtMeta

logging.basicConfig(level=logging.INFO)

# --- Example: Filter for YouTube Shorts (duration <= 60s) ---

# This example demonstrates how to find videos that are likely to be
# "YouTube Shorts" by filtering for a duration of 60 seconds or less.

print("--- Example: Filtering for 'YouTube Shorts' (duration <= 60s) ---")
client = YtMeta()

# A channel known to have a mix of long videos and shorts
channel_url = "https://www.youtube.com/@mkbhd/videos"

# Find videos that are between 1 and 60 seconds long.
shorts_filter = {"duration_seconds": {"lte": 60, "gt": 0}}

# No need for full metadata, as duration ('lengthSeconds') is available
# in the basic video info. This makes the query very fast.
videos = client.get_channel_videos(
    channel_url,
    filters=shorts_filter,
    fetch_full_metadata=False,
)

# Take the first 5 videos that match the filter
filtered_videos = list(itertools.islice(videos, 5))

print(f"Found {len(filtered_videos)} 'Shorts' (<= 60 seconds) (showing first 5):")
for video in filtered_videos:
    duration = video.get("duration_seconds")
    print(f"- Title: {video.get('title')}")
    print(f"  Duration: {duration}s")
    print(f"  URL: {video.get('url')}")

if not filtered_videos:
    print("No shorts found in the first batch of videos from this channel.")
