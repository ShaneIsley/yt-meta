import itertools
import logging

from yt_meta import YtMeta

# Enable logging to see the process
logging.basicConfig(level=logging.INFO)

# --- Example: Filter channel videos by view count ---

# This example demonstrates how to use the `filters` dictionary to fetch
# videos that meet specific criteria, like having more than a certain
# number of views.

print("--- Example: Filtering a channel by view count > 1,000,000 ---")
client = YtMeta()

# A channel known for having many videos with high view counts
channel_url = "https://www.youtube.com/@TED/videos"

# Define a filter to find videos with over 1,000,000 views.
# The `gt` stands for "greater than".
# Other operators include: `lt` (less than), `gte` (>=), `lte` (<=), `eq` (==)
filters = {"view_count": {"gt": 1_000_000}}

# No need for full metadata, as the basic info from the channel page
# includes the view count. This makes the query very fast.
videos_generator = client.get_channel_videos(
    channel_url,
    filters=filters,
    fetch_full_metadata=False,
)

# Take the first 5 videos that match the filter for this example
filtered_videos = list(itertools.islice(videos_generator, 5))

print(f"Found {len(filtered_videos)} videos with over 1M views (showing first 5):")
for video in filtered_videos:
    view_count = video.get("view_count")
    # Format the view count with commas for readability
    formatted_views = f"{view_count:,}" if view_count is not None else "N/A"

    print(f"- Title: {video.get('title')}")
    print(f"  Views: {formatted_views}")
    print(f"  URL: {video.get('url')}")

print("\nThis demonstrates how to apply advanced filters without needing to fetch full video metadata.")
