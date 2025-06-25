import itertools
from yt_meta import YtMetaClient

# Example: Find videos by filtering on their category.
# This is a "slow" filter because the category is not available on the
# main channel page. This means the client must fetch the full metadata for
# each video, which is slower.

client = YtMetaClient()
# Using a channel with a clear variety of categories
channel_url = "https://www.youtube.com/@MrBeast/videos"

filters = {
    "category": {"eq": "Entertainment"}
}

# The client will automatically set `fetch_full_metadata=True` because "category"
# is a slow filter.
print(f"Finding videos on {channel_url} in the 'Entertainment' category...")
videos = client.get_channel_videos(channel_url, filters=filters)

for video in itertools.islice(videos, 5):
    title = video.get('title', 'N/A')
    category = video.get('category', 'N/A')
    print(f"- '{title}' (Category: {category})") 