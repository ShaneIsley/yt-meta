"""
Example: Filter channel videos by description text

full_description is a slow filter: the listing has no description text (the
description_snippet fast filter was removed in 0.8.0), so each video checked
costs one metadata request. max_videos caps the results, not the videos
scanned, so a rare term can scan the whole channel.
"""

import itertools

from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Substring match (case-insensitive).
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


# Regex match: "AI" or "LLM" as whole words.
filters_re = {"full_description": {"re": r"\b(AI|LLM)\b"}}

print(f"\nFinding videos on {channel_url} using a regex for AI/LLM...")

videos_re = client.get_channel_videos(channel_url, filters=filters_re, max_videos=3)

for video in itertools.islice(videos_re, 3):
    desc = (video.get("full_description") or "")[:80]
    print(f"- Title: {video.get('title')}")
    print(f"  Description: {desc}\n")
