"""
Example: Filter channel videos by category

category is a slow filter: it needs each video's full metadata, one extra
request per video checked.
"""

import itertools

from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# This channel's videos are usually in "Science & Technology".
filters = {"category": {"eq": "Science & Technology"}}

print(f"Finding 'Science & Technology' category videos from {channel_url}...")
videos = client.get_channel_videos(channel_url, filters=filters, max_videos=10)

for video in itertools.islice(videos, 3):
    print(f"- '{video.get('title')}' (Category: {video.get('category')})")
