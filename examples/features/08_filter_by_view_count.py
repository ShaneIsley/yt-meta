"""
Example: Filter channel videos by view count

view_count is a fast filter: the channel listing already shows it, so no
extra request per video is needed.
"""

import itertools
import logging

from yt_meta import YtMeta

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

client = YtMeta()

# TED has many videos above a million views.
channel_url = "https://www.youtube.com/@TED/videos"

# Other numeric operators: lt, gte, lte, eq.
filters = {"view_count": {"gt": 1_000_000}}

print("Filtering channel videos by view count > 1,000,000")
print(f"Channel: {channel_url}\n")

videos_generator = client.get_channel_videos(
    channel_url,
    filters=filters,
    fetch_full_metadata=False,
)

filtered_videos = list(itertools.islice(videos_generator, 5))

print(f"Found {len(filtered_videos)} videos with over 1M views (showing first 5):\n")

for i, video in enumerate(filtered_videos, 1):
    view_count = video.get("view_count")
    formatted_views = f"{view_count:,}" if view_count is not None else "N/A"
    title = video.get("title", "No Title")
    url = video.get("url", "N/A")

    print(f"{i}. {title}")
    print(f"    Views: {formatted_views}")
    print(f"    URL: {url}")
    print()
