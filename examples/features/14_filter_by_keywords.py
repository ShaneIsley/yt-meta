import itertools

from yt_meta import YtMeta

# Example: Find videos by filtering on their keywords (tags).
# This is a "slow" filter because keywords require fetching full metadata.

if __name__ == "__main__":
    client = YtMeta()
    channel_url = "https://www.youtube.com/@samwitteveenai/videos"

    # --- Example 1: Find videos with a specific keyword ---
    print(f"Finding videos on {channel_url} with 'AI' keyword...")
    filters_any = {"keywords": {"contains_any": ["AI"]}}
    videos_any = client.get_channel_videos(
        channel_url, filters=filters_any, fetch_full_metadata=True, max_videos=10
    )
    for video in itertools.islice(videos_any, 5):
        print(f"- Found video: {video['title']}")

    # --- Example 2: Find videos with ALL of the specified keywords ---
    print(
        f"\nFinding videos on {channel_url} with 'google' AND 'gemini' keywords..."
    )
    filters_all = {"keywords": {"contains_all": ["google", "gemini"]}}
    videos_all = client.get_channel_videos(
        channel_url, filters=filters_all, fetch_full_metadata=True, max_videos=20
    )
    for video in itertools.islice(videos_all, 5):
        print(f"- Found video: {video['title']}")
