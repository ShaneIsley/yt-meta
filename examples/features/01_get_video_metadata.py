# examples/features/01_get_video_metadata.py

from yt_meta import YtMeta
from rich.pretty import pprint

# --- 1. Initialize the client ---
# You only need to create one instance of the client for your application.
client = YtMeta()

# --- 2. Define the video URL ---
# This can be any standard YouTube video URL.
video_url = "https://www.youtube.com/watch?v=B68agR-OeJM"  # Metrik & Linguistics @ Hospitality

# --- 3. Fetch the metadata ---
# This single call fetches the page and parses the data.
print(f"Fetching metadata for video: {video_url}\n")
video_meta = client.get_video_metadata(video_url)

# --- 4. Print the results ---
# The result is a dictionary containing all the extracted data.
if video_meta:
    pprint(video_meta)
