"""
This example demonstrates how to use multi-component filters, such as
a numerical range, which was fixed to behave as a logical AND.

You can specify multiple conditions for a single field, and the library
will ensure that all of them are met for an item to be included in the
results.
"""
import itertools
from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@TED/videos"

# Find videos with a view count between 500,000 and 510,000.
# This requires both the 'gt' (greater than) and 'lt' (less than)
# conditions to be true.
range_filters = {
    "view_count": {
        "gt": 500_000,
        "lt": 510_000
    }
}

print(f"Finding videos on {channel_url} with views between 500k and 510k...")

videos_generator = client.get_channel_videos(
    channel_url,
    filters=range_filters
)

# This is a fast filter, so the query is efficient.
for video in itertools.islice(videos_generator, 5):
    views = video.get('view_count', 0)
    print(f"- '{video.get('title')}' ({views:,} views)")

print("\nMulti-component filter demonstration complete.") 