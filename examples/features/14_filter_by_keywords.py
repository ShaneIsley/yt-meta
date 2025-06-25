import itertools
from yt_meta import YtMetaClient

# Example: Find videos by filtering on their keywords (tags).
# This is a "slow" filter because keywords require fetching full metadata.

client = YtMetaClient()
channel_url = "https://www.youtube.com/@dave2d/videos"

# --- Example 1: Find videos that have ANY of the specified keywords ---
filters_any = {
    "keywords": {"contains_any": ["review", "unboxing"]}
}

# The client will automatically set `fetch_full_metadata=True`
print(f"Finding videos on {channel_url} with 'review' or 'unboxing' keywords...")
videos_any = client.get_channel_videos(channel_url, filters=filters_any)

for video in itertools.islice(videos_any, 5):
    title = video.get('title', 'N/A')
    keywords = video.get('keywords', [])
    print(f"- '{title}' (Keywords: {keywords})")


# --- Example 2: Find videos that have ALL of the specified keywords ---
filters_all = {
    "keywords": {"contains_all": ["apple", "vision pro"]}
}

print(f"\nFinding videos on {channel_url} with 'apple' AND 'vision pro' keywords...")
videos_all = client.get_channel_videos(channel_url, filters=filters_all)

for video in itertools.islice(videos_all, 5):
    title = video.get('title', 'N/A')
    keywords = video.get('keywords', [])
    print(f"- '{title}' (Keywords: {keywords})") 