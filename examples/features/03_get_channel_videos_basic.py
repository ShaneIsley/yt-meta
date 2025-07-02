"""
Example: Basic Channel Video Fetching

This example demonstrates how to fetch videos from a YouTube channel's 
"Videos" tab using the basic functionality.

Key concepts:
• Channel video fetching  
• Generator-based iteration
• Basic video metadata access
• Memory-efficient processing
"""

import itertools

from yt_meta import YtMeta

# --- 1. Initialize the client ---
client = YtMeta()

# --- 2. Define the channel URL ---
# This can point to any channel's "/videos" page
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# --- 3. Get the video generator ---
# This method returns a generator, which is memory-efficient
# It doesn't fetch all videos at once
print(f"Fetching videos from: {channel_url}\n")
videos_generator = client.get_channel_videos(channel_url)

# --- 4. Iterate and display results ---
# We use itertools.islice to take just the first 10 videos
# This prevents a long-running script if the channel has many videos
print("--- First 10 Videos ---")
for i, video in enumerate(itertools.islice(videos_generator, 10), 1):
    # The dictionary for each video contains simplified metadata
    video_id = video.get("video_id", "N/A")
    title = video.get("title", "No Title")
    views = video.get("view_count", "N/A")
    published = video.get("published_time_text", "N/A")

    print(f"{i}. {title}")
    print(f"    ID: {video_id} | Views: {views} | Published: {published}")
    print()

print("✅ Channel video fetching complete!")
