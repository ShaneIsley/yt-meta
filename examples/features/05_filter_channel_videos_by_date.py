# examples/features/05_filter_channel_videos_by_date.py
import itertools
from datetime import date, timedelta

from yt_meta import YtMetaClient

# --- 1. Initialize the client ---
client = YtMetaClient()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# --- Use Case 1: Fetch videos from the last 30 days ---
# We use a simple shorthand string "30d".
# The library efficiently stops paginating once it finds videos older than this.
print(f"--- Fetching videos from the last 30 days from {channel_url} ---\n")
recent_videos_generator = client.get_channel_videos(channel_url, start_date="30d")

# We'll just look at the first 5 results for this example
for video in itertools.islice(recent_videos_generator, 5):
    title = video.get("title", "N/A")
    published = video.get("publishedTimeText", "N/A")
    print(f"- Title: {title}")
    print(f"  Published: {published}\n")


# --- Use Case 2: Fetch videos from a specific window in the past ---
# We define a precise window using date objects: from 90 days ago to 60 days ago.
print("\n--- Fetching videos from a 30-day window in the past ---\n")
start_window = date.today() - timedelta(days=90)
end_window = date.today() - timedelta(days=60)

past_videos_generator = client.get_channel_videos(channel_url, start_date=start_window, end_date=end_window)

for video in itertools.islice(past_videos_generator, 5):
    title = video.get("title", "N/A")
    published = video.get("publishedTimeText", "N/A")
    print(f"- Title: {title}")
    print(f"  Published: {published}\n")
