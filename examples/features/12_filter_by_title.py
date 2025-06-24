import itertools
from yt_meta import YtMetaClient

# Example: Find videos by filtering on their titles.
# This is a "fast" filter because the title is available on the main channel
# page, avoiding extra requests.

client = YtMetaClient()
channel_url = "https://www.youtube.com/@coreyms/videos"

# --- Example 1: Using the 'contains' operator ---
filters_contains = {
    "title": {"contains": "git"}
}

print(f"Finding videos on {channel_url} with 'Git' in the title...")

videos_contains = client.get_channel_videos(
    channel_url,
    filters=filters_contains,
    fetch_full_metadata=False
)

for video in itertools.islice(videos_contains, 5):
    print(f"- {video.get('title')}")


# --- Example 2: Using a regular expression ---
# Find videos that start with "Python"
filters_re = {
    "title": {"re": r"^Python"}
}

print(f"\nFinding videos on {channel_url} that start with 'Python'...")

videos_re = client.get_channel_videos(
    channel_url,
    filters=filters_re,
    fetch_full_metadata=False
)

for video in itertools.islice(videos_re, 5):
    print(f"- {video.get('title')}") 