"""
Example: Filter channel videos by full description

full_description is a slow filter, so the client turns on
fetch_full_metadata and makes one extra request per video checked.
start_date bounds the scan.
"""

import itertools

from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

filters = {"full_description": {"contains": "LangChain"}}

print(f"Finding videos on {channel_url} with 'LangChain' in the full description...")
print("This fetches each video's page, so it is slower than a listing-only filter.\n")

videos = client.get_channel_videos(
    channel_url, filters=filters, start_date="6 months ago", max_videos=3
)

print("Matching videos:")
count = 0
for video in itertools.islice(videos, 3):
    count += 1
    title = video.get("title", "N/A")
    description_snippet = " ".join(video.get("full_description", "").split()[:20])

    print(f"{count}. '{title}'")
    print(f"    Description snippet: '{description_snippet}...'")
    print()

if count == 0:
    print("No videos found with 'LangChain' in the description.")
    print("Try searching for 'AI', 'machine learning', or 'python' instead.")
else:
    print(f"Found {count} videos matching the description filter.")
