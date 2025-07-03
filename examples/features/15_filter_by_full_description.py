"""
Example: Filtering by Full Description

This example demonstrates how to filter videos based on their full description
content. This is a "slow" filter that requires fetching complete metadata.

Key concepts:
• Full description filtering
• Slow vs fast filters
• Automatic metadata fetching
• Content-based video discovery
"""

import itertools

from yt_meta import YtMeta

# --- 1. Initialize the client ---
client = YtMeta()

# --- 2. Define the channel and filter ---
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Find videos where the full description contains "LangChain"
# This is useful for finding videos that mention specific technologies or topics
filters = {"full_description": {"contains": "LangChain"}}

# --- 3. Fetch filtered videos ---
# The client will automatically set `fetch_full_metadata=True` for slow filters
print(f"Finding videos on {channel_url} with 'LangChain' in the full description...")
print("Note: This may take longer as full metadata is required.\n")

videos = client.get_channel_videos(channel_url, filters=filters, max_videos=20)

# --- 4. Display results ---
print("--- Matching Videos ---")
count = 0
for video in itertools.islice(videos, 5):
    count += 1
    title = video.get("title", "N/A")
    # Show a snippet of the description to confirm the match
    description_snippet = " ".join(video.get("full_description", "").split()[:20])

    print(f"{count}. '{title}'")
    print(f"    Description snippet: '{description_snippet}...'")
    print()

if count == 0:
    print("No videos found with 'LangChain' in the description.")
    print("Try searching for 'AI', 'machine learning', or 'python' instead.")
else:
    print(f"✅ Found {count} videos matching the description filter!")
