import itertools

from yt_meta import YtMeta

# Example: Find videos by filtering on their keywords (tags).
# This is a "slow" filter: keywords require fetching full metadata, so
# EVERY scanned video costs one request until enough matches are found.
# Always bound the scan (start_date here) to keep request counts sane.

if __name__ == "__main__":
    client = YtMeta()
    channel_url = "https://www.youtube.com/@samwitteveenai/videos"

    # --- Example 1: Find videos with a specific keyword ---
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

    # --- Example 2: Find videos with ALL of the specified keywords ---
    print(
        f"\nFinding videos on {channel_url} with 'google' AND 'gemini' keywords..."
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
