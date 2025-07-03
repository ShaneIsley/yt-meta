"""
Example: Basic Channel Metadata Fetching

This example demonstrates how to fetch comprehensive metadata for a
YouTube channel, including title, description, and channel statistics.

Key concepts:
• Channel metadata extraction
• Error handling for network issues
• Channel information access
• Basic channel analysis
"""

import logging

from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# --- 1. Initialize the client ---
client = YtMeta()

# --- 2. Define the channel URL ---
# This can be the URL to the channel's homepage or its "Videos" tab.
channel_url = "https://www.youtube.com/@hospitalrecords"

# --- 3. Fetch the metadata ---
try:
    logger.info(f"Fetching metadata for channel: {channel_url}")
    metadata = client.get_channel_metadata(channel_url)

    # --- 4. Print the results ---
    # The result is a dictionary containing the channel's metadata.
    print("\n✅ Channel metadata successfully retrieved:")
    print(f"        Title: {metadata['title']}")
    print(f"   Channel ID: {metadata['channel_id']}")
    print(f"   Vanity URL: {metadata['vanity_url']}")
    print(f"Family Safe?: {metadata['is_family_safe']}")
    print(f"     Keywords: {metadata.get('keywords', 'N/A')}")
    print(f"\n--- Description ---\n{metadata['description']}")

except Exception as e:
    logger.error(f"Failed to fetch channel metadata: {e}")
    print(f"❌ Error: Could not fetch metadata from {channel_url}")
    print("   Please check the channel URL and your internet connection")
