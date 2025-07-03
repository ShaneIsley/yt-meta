# examples/features/04_get_channel_videos_full_metadata.py
import itertools
import logging

from yt_meta import YtMeta

# --- Optional: Configure logging to see what's happening ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- 1. Initialize the client ---
client = YtMeta()

# --- 2. Define the channel URL ---
# We'll fetch from a channel with good metadata variety
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# --- 3. Get the video generator with full metadata ---
# Setting `fetch_full_metadata=True` gets additional data like likes, category, etc.
print(f"Fetching videos with full metadata from: {channel_url}\n")
videos_generator = client.get_channel_videos(
    channel_url,
    fetch_full_metadata=True,  # This enables "slow" filters
)

# --- 4. Iterate and print the enriched results ---
print("--- First 5 Videos with Full Metadata ---")
for video in itertools.islice(videos_generator, 5):
    # Now we have access to additional metadata fields
    video_id = video.get("video_id", "N/A")
    title = video.get("title", "No Title")
    views = video.get("view_count", "N/A")
    likes = video.get("like_count", "N/A")
    category = video.get("category", "N/A")

    print(f"- Title: {title}")
    print(
        f"  Info: (ID: {video_id}) - Views: {views:,} - Likes: {likes:,} - Category: {category}\n"
    )

print("Note: Full metadata fetching takes longer but provides richer data.")
