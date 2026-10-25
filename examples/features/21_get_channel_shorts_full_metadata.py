"""
Example: Channel Shorts with full metadata

Lists Shorts with fetch_full_metadata=True, which adds publish date, likes,
category and duration at one extra request per Short. That also allows
filters on those fields, such as like_count.
"""

from yt_meta import YtMeta

yt_meta = YtMeta()

channel_url = "https://www.youtube.com/@bashbunni"

print(f"Fetching shorts for {channel_url} with full metadata (one request per Short)...")

try:
    shorts_generator = yt_meta.get_channel_shorts(
        channel_url,
        fetch_full_metadata=True,
        # like_count is not in the Shorts listing, so this filter needs the full fetch.
        filters={"like_count": {"gt": 100}},
        max_videos=5,
    )

    for i, short in enumerate(shorts_generator):
        print(f"  - Short {i + 1}:")
        print(f"    - Title: {short['title']}")
        print(f"    - Video ID: {short['video_id']}")
        print(f"    - View Count: {short.get('view_count', 'N/A')}")
        print(f"    - URL: {short['url']}")
        # Fields below come from the per-Short request.
        print(f"    - Publish Date: {short.get('publish_date', 'N/A')}")
        print(f"    - Like Count: {short.get('like_count', 'N/A')}")
        print(f"    - Category: {short.get('category', 'N/A')}")
        print(f"    - Duration (s): {short.get('duration_seconds', 'N/A')}")
        print()

except Exception as e:
    print(f"An error occurred: {e}")
