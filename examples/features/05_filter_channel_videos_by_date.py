"""
Example: Filter channel videos by publish date

Shows a "last 30 days" filter and a fixed past window. Both pass
fetch_full_metadata=True, so the exact date decides and each candidate video
costs one extra request. Pagination stops once the listing is older than the
window.
"""

import itertools
from datetime import date, timedelta

from yt_meta import YtMeta
from yt_meta.date_utils import parse_relative_date_string

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Last 30 days, from the shorthand string "30d".
print(f"Videos from the last 30 days on {channel_url}:\n")
thirty_days_ago = parse_relative_date_string("30d")
date_filter = {"publish_date": {"gte": thirty_days_ago}}
recent_videos_generator = client.get_channel_videos(
    channel_url, fetch_full_metadata=True, filters=date_filter
)

for video in itertools.islice(recent_videos_generator, 5):
    title = video.get("title", "N/A")
    published = video.get("publish_date", "N/A")
    print(f"- Title: {title}")
    print(f"  Published: {published}\n")


# A fixed window in the past: from 90 days ago to 60 days ago.
print("\nVideos from a 30-day window in the past:\n")
start_window = date.today() - timedelta(days=90)
end_window = date.today() - timedelta(days=60)

date_filter = {"publish_date": {"gte": start_window, "lte": end_window}}
past_videos_generator = client.get_channel_videos(
    channel_url, fetch_full_metadata=True, filters=date_filter
)

for video in itertools.islice(past_videos_generator, 5):
    title = video.get("title", "N/A")
    published = video.get("publish_date", "N/A")
    print(f"- Title: {title}")
    print(f"  Published: {published}\n")
