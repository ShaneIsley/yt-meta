import itertools

from yt_meta import YtMeta

# Example: Find videos by filtering on their category.
# Category is a "slow" filter because full metadata is required.

client = YtMeta()
channel_url = "https://www.youtube.com/@TED/videos"

# TED videos are typically in the "Education" category
filters = {"category": {"eq": "Education"}}

print(f"Finding 'Education' category videos from {channel_url}...")
videos = client.get_channel_videos(channel_url, filters=filters)

for video in itertools.islice(videos, 3):
    print(f"- '{video.get('title')}' (Category: {video.get('category')})")

print("\nNote: Category filtering requires full metadata, so it's slower.")
