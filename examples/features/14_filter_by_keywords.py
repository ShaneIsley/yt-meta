import itertools
from yt_meta import YtMetaClient

# Example: Find videos by filtering on their keywords (tags).
# This is a "slow" filter because keywords require fetching full metadata.

if __name__ == "__main__":
    client = YtMetaClient()
    channel_url = "https://www.youtube.com/@bashbunni/videos"

    # --- Example 1: Find videos with a specific keyword ---
    print(f"Finding videos on {channel_url} with 'programming' keyword...")
    filters_any = {
        "title": {"contains": "programming"}
    }
    videos_any = client.get_channel_videos(channel_url, filters=filters_any)
    for video in itertools.islice(videos_any, 5):
        print(f"- Found in title: {video['title']}")

    # --- Example 2: Find videos with ALL of the specified keywords in the title ---
    print(f"\nFinding videos on {channel_url} with 'open source' AND 'project' keywords...")
    # The library's filters currently check for one condition per field.
    # To check for multiple conditions (an "AND" operation), you can chain them in your code.
    
    # First, filter for videos containing 'open source'
    videos_with_os = client.get_channel_videos(channel_url, filters={"title": {"contains": "open source"}})
    
    # Then, use a generator expression to filter those results for 'project'
    videos_with_both = (v for v in videos_with_os if "project" in v.get('title', '').lower())

    for video in itertools.islice(videos_with_both, 5):
        print(f"- Found in title: {video['title']}") 