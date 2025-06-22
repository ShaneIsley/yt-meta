# examples/features/01_get_video_metadata.py

from yt_meta import YtMetaClient

# --- 1. Initialize the client ---
# You only need to create one instance of the client for your application.
client = YtMetaClient()

# --- 2. Define the video URL ---
# This can be any standard YouTube video URL.
video_url = "https://www.youtube.com/watch?v=B68agR-OeJM"  # Metrik & Linguistics @ Hospitality

# --- 3. Fetch the metadata ---
# This single call fetches the page and parses the data.
print(f"Fetching metadata for video: {video_url}\n")
metadata = client.get_video_metadata(video_url)

# --- 4. Print the results ---
# The result is a dictionary containing all the extracted data.
print(f"          Title: {metadata['title']}")
print(f"  Channel (ID): {metadata['channel_name']} ({metadata['channel_id']})")
print(f"        Views: {metadata['view_count']:,}")
print(f"        Likes: {metadata.get('like_count', 'N/A'):,}")
print(f"     Duration: {metadata['duration_seconds']} seconds")
print(f"     Category: {metadata['category']}")
print(f"  Publish Date: {metadata['publish_date']}")
print(f"\n--- Description Snippet ---\n{metadata['full_description'][:200]}...")
