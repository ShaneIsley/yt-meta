"""
Example: Filter channel videos by title

title is a fast filter: the listing carries it, so no extra request per
video is needed. Both contains and re match case-insensitively.
"""

import itertools

from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

filters = {"title": {"contains": "python"}}

print(f"Finding videos on {channel_url} with 'python' in the title...")
videos = client.get_channel_videos(channel_url, filters=filters, max_videos=50)

count = 0
for video in itertools.islice(videos, 5):
    count += 1
    title = video.get("title", "N/A")
    print(f"{count}. '{title}'")

if count == 0:
    print("No videos found with 'python' in the title. Try 'AI' or 'machine' instead.")

# Titles that start with "Python".
filters_re = {"title": {"re": r"^Python"}}

print(f"\nFinding videos on {channel_url} that start with 'Python'...")

videos_re = client.get_channel_videos(
    channel_url, filters=filters_re, fetch_full_metadata=False, max_videos=50
)

for video in itertools.islice(videos_re, 5):
    print(f"- {video.get('title')}")
