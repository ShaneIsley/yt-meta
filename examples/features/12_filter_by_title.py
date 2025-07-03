import itertools

from yt_meta import YtMeta

# Example: Find videos by filtering on their title.
# This is a "fast" filter because the title is available on the main channel
# page, avoiding extra requests.

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Find videos with "python" in the title (case-insensitive).
# Title filtering is a "fast" filter since title is available in the basic video data.
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

# --- Example 2: Using a regular expression ---
# Find videos that start with "Python"
filters_re = {"title": {"re": r"^Python"}}

print(f"\nFinding videos on {channel_url} that start with 'Python'...")

videos_re = client.get_channel_videos(
    channel_url, filters=filters_re, fetch_full_metadata=False, max_videos=50
)

for video in itertools.islice(videos_re, 5):
    print(f"- {video.get('title')}")
