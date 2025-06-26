import itertools

from yt_meta import YtMeta

# Example: Find videos by filtering on their keywords (tags).
# This is a "slow" filter because keywords require fetching full metadata.

if __name__ == "__main__":
    client = YtMeta()
    channel_url = "https://www.youtube.com/@bashbunni/videos"

    # --- Example 1: Find videos with a specific keyword ---
    print(f"Finding videos on {channel_url} with 'programming' keyword...")
    filters_any = {
        "keywords": {"contains_any": ["programming"]}
    }
    videos_any = client.get_channel_videos(channel_url, filters=filters_any, fetch_full_metadata=True)
    for video in itertools.islice(videos_any, 5):
        print(f"- Found video: {video['title']}")

    # --- Example 2: Find videos with ALL of the specified keywords ---
    print(f"\nFinding videos on {channel_url} with 'open source' AND 'project' keywords...")
    filters_all = {
        "keywords": {"contains_all": ["open source", "project"]}
    }
    videos_all = client.get_channel_videos(channel_url, filters=filters_all, fetch_full_metadata=True)
    for video in itertools.islice(videos_all, 5):
        print(f"- Found video: {video['title']}") 