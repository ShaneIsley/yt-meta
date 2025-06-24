import itertools
import logging
from datetime import date, timedelta

from yt_meta import YtMetaClient

# Enable logging to see the process
logging.basicConfig(level=logging.INFO)

# --- Example 1: Get videos from a specific date window in a playlist ---

# This example demonstrates how to fetch videos from a playlist that were
# published within a specific date range.
# Note: Unlike channel filtering, playlist filtering requires fetching all
# videos first, as playlists are not guaranteed to be chronological.

print("--- Example: Filtering a playlist by a date range ---")
client = YtMetaClient()

# A well-known, long-running playlist for good test data
playlist_id = "PL_6zDbB-zRecNEf1VIkum2bpgDbOBXsI4"

# Define a date window, e.g., all of 2020
start_date = date(2024, 1, 1)
end_date = date(2024, 12, 31)

# Set fetch_full_metadata=True to get the precise `publish_date`
videos_generator = client.get_playlist_videos(
    playlist_id,
    start_date=start_date,
    end_date=end_date,
    fetch_full_metadata=True,
)

# Use itertools.islice to get just the first 5 results for this example
filtered_videos = list(itertools.islice(videos_generator, 5))

print(f"Found {len(filtered_videos)} videos from the playlist published in 2020 (showing first 5):")
for video in filtered_videos:
    # Extract the date part from the ISO format datetime string
    publish_date = video.get("publish_date", "N/A").split("T")[0]
    print(f"- Title: {video.get('title')}")
    print(f"  Published: {publish_date}")
    print(f"  URL: {video.get('watchUrl')}")

print("\nNote: If no videos were found, it may be there are none in that date range in the first part of the playlist") 