"""
Example: Filtering by View Count

This example demonstrates how to filter videos based on view count thresholds.
This is a "fast" filter that uses data already available on the channel page.

Key concepts:
• View count filtering with numeric operators
• Fast vs slow filters
• Efficient querying without full metadata
• Formatted number display
"""

import itertools
import logging

from yt_meta import YtMeta

# Configure logging to see the process
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# --- 1. Initialize the client ---
client = YtMeta()

# --- 2. Define the channel and filter ---
# Using TED channel which has many videos with high view counts
channel_url = "https://www.youtube.com/@TED/videos"

# Define a filter to find videos with over 1,000,000 views
# The `gt` stands for "greater than"
# Other operators include: `lt` (less than), `gte` (>=), `lte` (<=), `eq` (==)
filters = {"view_count": {"gt": 1_000_000}}

print("--- Filtering channel videos by view count > 1,000,000 ---")
print(f"Channel: {channel_url}\n")

# --- 3. Fetch filtered videos ---
# No need for full metadata as view count is available on the channel page
# This makes the query very fast
videos_generator = client.get_channel_videos(
    channel_url,
    filters=filters,
    fetch_full_metadata=False,
)

# --- 4. Display results ---
# Take the first 5 videos that match the filter for this example
filtered_videos = list(itertools.islice(videos_generator, 5))

print(f"Found {len(filtered_videos)} videos with over 1M views (showing first 5):")
print("=" * 60)

for i, video in enumerate(filtered_videos, 1):
    view_count = video.get("view_count")
    # Format the view count with commas for readability
    formatted_views = f"{view_count:,}" if view_count is not None else "N/A"
    title = video.get("title", "No Title")
    url = video.get("url", "N/A")

    print(f"{i}. {title}")
    print(f"    Views: {formatted_views}")
    print(f"    URL: {url}")
    print()

print("✅ This demonstrates advanced filtering without fetching full video metadata!")
print("   Fast filters use data already available on the channel page.")
