"""
Example: Basic Video Metadata Fetching

This example demonstrates how to fetch comprehensive metadata for a single 
YouTube video. This is the most basic operation in the library.

Key concepts:
• Video metadata extraction
• Error handling for unavailable videos
• Rich data visualization
• Exception handling patterns
"""

import logging

from rich.pretty import pprint

from yt_meta import YtMeta
from yt_meta.exceptions import VideoUnavailableError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- 1. Initialize the client ---
# You only need to create one instance of the client for your application.
client = YtMeta()

# --- 2. Define the video URL ---
# This can be any standard YouTube video URL.
video_url = "https://www.youtube.com/watch?v=B68agR-OeJM"  # Metrik & Linguistics @ Hospitality

# --- 3. Fetch the metadata ---
try:
    logger.info(f"Fetching metadata for video: {video_url}")
    video_meta = client.get_video_metadata(video_url)
    
    # --- 4. Print the results ---
    # The result is a dictionary containing all the extracted data.
    if video_meta:
        print("\n✅ Video metadata successfully retrieved:")
        pprint(video_meta)
    else:
        print("⚠️  No metadata found for this video.")
        
except VideoUnavailableError as e:
    logger.error(f"Video unavailable: {e}")
    print(f"❌ Error: Video at {video_url} is not accessible")
    print("   This could be due to: private video, deleted video, or regional restrictions")
    
except Exception as e:
    logger.error(f"Unexpected error fetching video metadata: {e}")
    print(f"❌ Error: Failed to fetch metadata from {video_url}")
    print("   Please check your internet connection and try again")
