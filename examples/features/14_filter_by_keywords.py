"""
Example: Filter channel videos by keywords (tags)

keywords is a slow filter: every video scanned costs one request until
enough match. start_date bounds the scan; max_videos only caps the results.
"""

import itertools

from yt_meta import YtMeta

if __name__ == "__main__":
    client = YtMeta()
    channel_url = "https://www.youtube.com/@samwitteveenai/videos"

    # contains_any: at least one of the keywords.
    print(f"Finding videos on {channel_url} with 'AI' keyword...")
    filters_any = {"keywords": {"contains_any": ["AI"]}}
    videos_any = client.get_channel_videos(
        channel_url,
        filters=filters_any,
        start_date="2 months ago",  # bound the scan window
        max_videos=5,
    )
    for video in itertools.islice(videos_any, 3):
        print(f"- Found video: {video['title']}")

    # contains_all: every one of the keywords.
    print(
        f"\nFinding videos on {channel_url} with both 'google' and 'gemini' keywords..."
    )
    filters_all = {"keywords": {"contains_all": ["google", "gemini"]}}
    videos_all = client.get_channel_videos(
        channel_url,
        filters=filters_all,
        start_date="2 months ago",
        max_videos=5,
    )
    for video in itertools.islice(videos_all, 3):
        print(f"- Found video: {video['title']}")
