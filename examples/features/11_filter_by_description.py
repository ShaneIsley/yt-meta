import itertools

from yt_meta import YtMeta

# Example: Find videos with a specific keyword in their description.
#
# Description filtering uses `full_description`, a SLOW filter: the
# listing page carries no description text on current YouTube (the
# `description_snippet` fast filter was removed in 0.8.0), so each
# candidate video costs one metadata request. Bound the scan with
# max_videos to keep request counts predictable.

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# --- Example 1: Using the 'contains' operator ---
filters_contains = {"full_description": {"contains": "Gemini"}}

print(f"Finding videos on {channel_url} with 'Gemini' in the description...")

videos_contains = client.get_channel_videos(
    channel_url,
    filters=filters_contains,
    max_videos=3,
)

for video in itertools.islice(videos_contains, 3):
    desc = (video.get("full_description") or "")[:80]
    print(f"- Title: {video.get('title')}")
    print(f"  Description: {desc}\n")


# --- Example 2: Using a regular expression ---
# Find videos that mention "AI" or "LLM" as whole words
filters_re = {"full_description": {"re": r"\b(AI|LLM)\b"}}

print(f"\nFinding videos on {channel_url} using a regex for AI/LLM...")

videos_re = client.get_channel_videos(channel_url, filters=filters_re, max_videos=3)

for video in itertools.islice(videos_re, 3):
    desc = (video.get("full_description") or "")[:80]
    print(f"- Title: {video.get('title')}")
    print(f"  Description: {desc}\n")
