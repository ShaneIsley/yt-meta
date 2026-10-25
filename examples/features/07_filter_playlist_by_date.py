"""
Example: Filter a playlist by publish date

Playlists aren't in date order, so a date filter scans the whole playlist
instead of stopping early. Without fetch_full_metadata the filter uses the
listing's approximate dates ("2 years ago") and costs no extra requests.
"""

import logging
from datetime import date

from yt_meta import YtMeta

logging.basicConfig(level=logging.INFO)

client = YtMeta()

# Corey Schafer's Python tutorials: about 160 videos from 2015 onwards.
playlist_id = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"
start_date = date(2024, 1, 1)

videos = list(
    client.get_playlist_videos(
        playlist_id,
        filters={"publish_date": {"gte": start_date}},
    )
)

print(f"{len(videos)} videos in the playlist published on or after {start_date}:")
for video in videos:
    print(f"- {video['title']} ({video['publish_date_text']})")
