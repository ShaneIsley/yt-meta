import itertools

from yt_meta import YtMeta

# Example: Find videos with a specific keyword in their description snippet.
# This is a "fast" filter because the description snippet is available on the
# main channel page, avoiding extra requests.

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# --- Example 1: Using the 'contains' operator ---
filters_contains = {"description_snippet": {"contains": "Gemini"}}

print(f"Finding videos on {channel_url} with 'Gemini' in the description...")

videos_contains = client.get_channel_videos(
    channel_url,
    filters=filters_contains,
    fetch_full_metadata=False,  # Keep it fast
    max_videos=50,
)

for video in itertools.islice(videos_contains, 5):
    desc = video.get("description_snippet", "")
    print(f"- Title: {video.get('title')}")
    print(f"  Snippet: {desc}\n")


# --- Example 2: Using a regular expression ---
# Find videos that mention "AI" or "Artificial Intelligence"
filters_re = {"description_snippet": {"re": r"\b(AI|LLM)\b"}}

print(f"\nFinding videos on {channel_url} using a regex for AI/LLM...")

videos_re = client.get_channel_videos(
    channel_url, filters=filters_re, fetch_full_metadata=False, max_videos=50
)

for video in itertools.islice(videos_re, 5):
    desc = video.get("description_snippet", "")
    print(f"- Title: {video.get('title')}")
    print(f"  Snippet: {desc}\n")
