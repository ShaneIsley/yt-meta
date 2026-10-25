"""
Example: Filter channel videos by like count

like_count is a slow filter: the listing doesn't show likes, so the client
fetches each video's page, one extra request per video. With only a slow
filter and no date bound, it fetches every video until 5 match.
"""

import itertools
import logging

from yt_meta import YtMeta

# INFO logging shows a "Fetching video page" line for each video checked.
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    client = YtMeta()
    channel_url = "https://www.youtube.com/@samwitteveenai/videos"

    print(f"Filtering {channel_url} by like count > 500")
    filters = {"like_count": {"gt": 500}}

    # max_videos caps the number of results, not the videos scanned; islice
    # below takes the first 5 anyway. Use start_date to bound the scan.
    videos = list(
        itertools.islice(
            client.get_channel_videos(channel_url, filters=filters, max_videos=20), 5
        )
    )

    print(f"Found {len(videos)} videos with over 500 likes (showing first 5):")
    for video in videos:
        print(f"- Title: {video.get('title')}")
        print(f"  Likes: {video.get('like_count'):,}")
        print(f"  URL: {video.get('url')}")
