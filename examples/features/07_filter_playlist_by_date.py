import itertools
import logging
from datetime import date

from yt_meta import YtMetaClient

# Enable logging to see the process
logging.basicConfig(level=logging.INFO)

# --- Example: Get videos from a specific date window in a channel ---
print("--- Example: Filtering a channel by a specific date range ---")
client = YtMetaClient()

channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Define a date window
start_date = date(2025, 4, 1)
end_date = date(2025, 6, 30)

# The `publish_date` filter is a 'slow' filter, but the library optimizes
# this by first using the 'fast' `published_time_text` to narrow down
# the search space before fetching full metadata for precise filtering.
date_filter = {"publish_date": {"gte": start_date, "lte": end_date}}
videos_generator = client.get_channel_videos(
    channel_url,
    filters=date_filter,
)

# Use itertools.islice to get just the first 5 results for this example
filtered_videos = list(itertools.islice(videos_generator, 5))

print(f"Found {len(filtered_videos)} videos from the channel published between {start_date} and {end_date} (showing first 5):")
for video in filtered_videos:
    publish_date = video.get("publish_date", "N/A")
    print(f"- Title: {video.get('title')}")
    print(f"  Published: {publish_date}")
    print(f"  URL: {video.get('url')}")

print("\nNote: If no videos were found, there may be none in that date range.") 