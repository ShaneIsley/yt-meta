"""
Example: Range filter

Gives one field two conditions (gt and lt) to select a view-count range. Every
condition on a field must hold for a video to be included.
"""

import itertools

from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

range_filters = {"view_count": {"gt": 10_000, "lt": 50_000}}

print(f"Finding videos on {channel_url} with views between 10k and 50k...")

videos_generator = client.get_channel_videos(
    channel_url, filters=range_filters, max_videos=50
)

# view_count is in the channel listing, so this filter costs no extra requests.
for video in itertools.islice(videos_generator, 5):
    views = video.get("view_count", 0)
    print(f"- '{video.get('title')}' ({views:,} views)")

print("\nDone.")
