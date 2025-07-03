"""
Example: Basic Playlist Video Fetching

This example demonstrates how to fetch videos from a YouTube playlist.
It shows the basic playlist functionality with memory-efficient iteration.

Key concepts:
• Playlist video fetching
• Generator-based iteration
• Basic video metadata access
"""

import itertools

from yt_meta import YtMeta

# --- 1. Initialize the client ---
client = YtMeta()

# --- 2. Define the playlist ---
# This example uses a Python programming tutorial playlist
playlist_id = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"

# --- 3. Fetch playlist videos ---
# The method returns a generator for memory efficiency
print(f"Fetching videos from playlist: {playlist_id}\n")
videos_generator = client.get_playlist_videos(playlist_id=playlist_id)

# --- 4. Display results ---
# We use itertools.islice to take just the first 10 videos
print("--- First 10 Videos ---")
for i, video in enumerate(itertools.islice(videos_generator, 10), 1):
    title = video.get("title", "No Title")
    url = video.get("url", "N/A")

    print(f"{i}. {title}")
    print(f"   URL: {url}")
    print()

print("✅ Playlist video fetching complete!")
