# (like 'like_count'), the client needs to fetch the full metadata for each
# video that passes the initial "fast" filters. This is more powerful but
# significantly slower.
 
# In this case, we are ONLY using a slow filter, so it will fetch full
# metadata for every video until it finds 5 that match.

import itertools
import logging

from yt_meta import YtMetaClient

# To see the client's activity, including fetching full metadata for each video,
# enable INFO-level logging. You will see a "Fetching video page" message for
# every video until 5 matches are found.
logging.basicConfig(level=logging.INFO)


print("--- Example: Filtering a channel by like count > 100,000 ---")
client = YtMetaClient()
channel_url = "https://www.youtube.com/@TED/videos"

# 'like_count' is a "slow" filter. The client will fetch basic metadata for
# videos first. Since there are no "fast" filters here, it will then proceed
# to fetch the full metadata for every video until it finds 5 that have
# more than 100,000 likes.

filters = {"like_count": {"gt": 100000}}

# We'll limit the search to 5 results for this example.
videos_generator = client.get_channel_videos(channel_url, filters=filters)
videos = list(itertools.islice(videos_generator, 5))


print("Found 5 videos with over 100K likes (showing first 5):")
for video in videos:
    print(f"- Title: {video.get('title')}")
    print(f"  Likes: {video.get('like_count'):,}")
    print(f"  URL: {video.get('url')}")

print("\nThis demonstrates how to apply a 'slow' filter, which automatically")
print("triggers fetching full metadata for videos.")