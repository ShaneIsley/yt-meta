# examples/features/02_get_channel_metadata.py

from yt_meta import YtMeta

# --- 1. Initialize the client ---
client = YtMeta()

# --- 2. Define the channel URL ---
# This can be the URL to the channel's homepage or its "Videos" tab.
channel_url = "https://www.youtube.com/@hospitalrecords"

# --- 3. Fetch the metadata ---
print(f"Fetching metadata for channel: {channel_url}\n")
metadata = client.get_channel_metadata(channel_url)

# --- 4. Print the results ---
# The result is a dictionary containing the channel's metadata.
print(f"        Title: {metadata['title']}")
print(f"   Channel ID: {metadata['channel_id']}")
print(f"   Vanity URL: {metadata['vanity_url']}")
print(f"Family Safe?: {metadata['is_family_safe']}")
print(f"     Keywords: {metadata.get('keywords', 'N/A')}")
print(f"\n--- Description ---\n{metadata['description']}")
