# (like 'like_count'), the client needs to fetch the full metadata for each
# video that passes the initial "fast" filters. This is more powerful but
# significantly slower.

# In this case, we are ONLY using a slow filter, so it will fetch full
# metadata for every video until it finds 5 that match.

import itertools
import logging

from yt_meta import YtMeta

# To see the client's activity, including fetching full metadata for each video,
# enable INFO-level logging. You will see a "Fetching video page" message for
# every video until 5 matches are found.
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    client = YtMeta()
    channel_url = "https://www.youtube.com/@bashbunni/videos"

    # --- Example: Filtering a channel by like count > 100 ---
    print(f"--- Example: Filtering {channel_url} by like count > 100 ---")
    filters = {"like_count": {"gt": 100}}

    # We only take the first 5 results for this example
    videos = list(itertools.islice(client.get_channel_videos(channel_url, filters=filters), 5))

    print(f"Found {len(videos)} videos with over 100 likes (showing first 5):")
    for video in videos:
        print(f"- Title: {video.get('title')}")
        print(f"  Likes: {video.get('like_count'):,}")
        print(f"  URL: {video.get('url')}")

    print("\nThis demonstrates how to apply a 'slow' filter, which automatically")
    print("triggers fetching full metadata for videos.")
