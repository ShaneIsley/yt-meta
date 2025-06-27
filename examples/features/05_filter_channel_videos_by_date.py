# examples/features/05_filter_channel_videos_by_date.py
import itertools
from datetime import date, timedelta

from yt_meta import YtMeta
from yt_meta.date_utils import parse_relative_date_string

# --- 1. Initialize the client ---
client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# --- Use Case 1: Fetch videos from the last 30 days ---
# We use a simple shorthand string "30d".
# The library efficiently stops paginating once it finds videos older than this.
print(f"--- Fetching videos from the last 30 days from {channel_url} ---\n")
thirty_days_ago = parse_relative_date_string("30d")
date_filter = {"publish_date": {"gte": thirty_days_ago}}
recent_videos_generator = client.get_channel_videos(channel_url, fetch_full_metadata=True, filters=date_filter)

# We'll just look at the first 5 results for this example
for video in itertools.islice(recent_videos_generator, 5):
    title = video.get("title", "N/A")
    published = video.get("published_time_text", "N/A")
    print(f"- Title: {title}")
    print(f"  Published: {published}\n")


# --- Use Case 2: Fetch videos from a specific window in the past ---
# We define a precise window using date objects: from 90 days ago to 60 days ago.
print("\n--- Fetching videos from a 30-day window in the past ---\n")
start_window = date.today() - timedelta(days=90)
end_window = date.today() - timedelta(days=60)

date_filter = {"publish_date": {"gte": start_window, "lte": end_window}}
past_videos_generator = client.get_channel_videos(channel_url, fetch_full_metadata=True, filters=date_filter)

for video in itertools.islice(past_videos_generator, 5):
    title = video.get("title", "N/A")
    published = video.get("published_time_text", "N/A")
    print(f"- Title: {title}")
    print(f"  Published: {published}\n")
