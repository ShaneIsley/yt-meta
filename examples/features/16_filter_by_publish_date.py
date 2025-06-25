import itertools
from yt_meta import YtMetaClient

# Example: Find videos by filtering on their publish date.
# `publish_date` is a special filter. It can be "fast" for rough checks
# to stop pagination, but becomes a "slow" filter for precise, per-video
# checks, which requires fetching full metadata.

client = YtMetaClient()
channel_url = "https://www.youtube.com/@ycombinator/videos"

# Find videos published on or after January 1st, 2024.
# This uses the `gte` (greater than or equal to) operator.
filters = {
    "publish_date": {"gte": "2024-01-01"}
}

# The client will automatically set `fetch_full_metadata=True` to ensure
# the date comparison is precise.
print(f"Finding videos on {channel_url} published on or after 2024-01-01...")
videos = client.get_channel_videos(channel_url, filters=filters)

for video in itertools.islice(videos, 5):
    title = video.get('title', 'N/A')
    p_date = video.get('publish_date', 'N/A')
    print(f"- '{title}' (Published: {p_date})") 