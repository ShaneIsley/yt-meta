import itertools
import logging

from yt_meta import YtMeta

logging.basicConfig(level=logging.INFO)

# --- Example: Filter for YouTube Shorts (duration <= 60s) ---

# This example demonstrates how to find videos that are likely to be
# "YouTube Shorts" by filtering for a duration of 60 seconds or less.

print("--- Example: Filtering for 'YouTube Shorts' (duration <= 60s) ---")
client = YtMeta()

# TED videos often have consistent durations for their talks
channel_url = "https://www.youtube.com/@TED/videos"

# Find videos between 10 and 20 minutes long
duration_filter = {
    "duration_seconds": {
        "gte": 10 * 60,  # 10 minutes in seconds
        "lte": 20 * 60   # 20 minutes in seconds
    }
}

print(f"Finding videos on {channel_url} between 10-20 minutes long...")
videos_generator = client.get_channel_videos(
    channel_url,
    filters=duration_filter
)

# Get the first 5 matching videos
matching_videos = list(itertools.islice(videos_generator, 5))

print(f"Found {len(matching_videos)} videos between 10-20 minutes (showing all):")
for i, video in enumerate(matching_videos, 1):
    duration = video.get("duration_seconds", 0)
    duration_text = video.get("duration_text", "N/A")
    title = video.get("title", "No Title")
    
    print(f"{i}. '{title}'")
    print(f"   Duration: {duration_text} ({duration} seconds)")
    print()

if len(matching_videos) == 0:
    print("No videos found in this duration range. TED talks vary in length.")
