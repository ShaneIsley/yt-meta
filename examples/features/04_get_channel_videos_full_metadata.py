# examples/features/04_get_channel_videos_full_metadata.py
import itertools
import logging

from yt_meta import YtMetaClient

# --- Optional: Configure logging to see what's happening ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- 1. Initialize the client ---
client = YtMetaClient()

# --- 2. Define the channel URL ---
# Using a channel with fewer videos to keep the example quick.
channel_url = "https://www.youtube.com/@TheAIEpiphany/videos"

# --- 3. Get the video generator with full metadata enabled ---
print(f"Fetching full metadata for videos from: {channel_url}\n")
videos_generator = client.get_channel_videos(channel_url, fetch_full_metadata=True)

# --- 4. Iterate and print the detailed results ---
# We'll take just the first 5 to keep the example fast.
print("--- First 5 Videos (Full Metadata) ---")
for video in itertools.islice(videos_generator, 5):
    # The dictionary for each video now contains the full metadata.
    if "error" in video:
        print(f"\nCould not fetch video (ID: {video.get('video_id', 'N/A')}): {video['error']}")
        continue

    video_id = video.get("video_id", "N/A")
    title = video.get("title", "No Title")
    views = video.get("view_count", "N/A")
    likes = video.get("like_count", "N/A")
    category = video.get("category", "N/A")

    print(f"- Title: {title}")
    print(f"  Info: (ID: {video_id}) - Views: {views:,} - Likes: {likes:,} - Category: {category}\n")
