# examples/features/03_get_channel_videos_basic.py
import itertools

from yt_meta import YtMetaClient

# --- 1. Initialize the client ---
client = YtMetaClient()

# --- 2. Define the channel URL ---
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# --- 3. Get the video generator ---
# This method returns a generator, which is memory-efficient.
# It doesn't fetch all videos at once.
print(f"Fetching videos from: {channel_url}\n")
videos_generator = client.get_channel_videos(channel_url)

# --- 4. Iterate and print the results ---
# We use itertools.islice to take just the first 10 videos.
# This prevents a long-running script if the channel has many videos.
print("--- First 10 Videos ---")
for video in itertools.islice(videos_generator, 10):
    # The dictionary for each video contains simplified metadata.
    video_id = video.get("video_id", "N/A")
    title = video.get("title", "No Title")
    views = video.get("view_count", "N/A")
    published = video.get("published_time_text", "N/A")

    print(f"- Title: {title}")
    print(f"  Info: (ID: {video_id}) - Views: {views} - Published: {published}\n")
