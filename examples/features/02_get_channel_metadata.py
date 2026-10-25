"""
Example: Channel metadata

get_channel_metadata returns the channel's title, description, channel
id, vanity URL, keywords and family-safe flag. It does not include
statistics such as subscriber or view counts.
"""

from yt_meta import VideoUnavailableError, YtMeta

client = YtMeta()

# The channel's home page or any of its tabs works.
channel_url = "https://www.youtube.com/@hospitalrecords"

try:
    metadata = client.get_channel_metadata(channel_url)
except VideoUnavailableError as e:
    raise SystemExit(f"Could not fetch {channel_url}: {e}") from e

print(f"Title:       {metadata['title']}")
print(f"Channel ID:  {metadata['channel_id']}")
print(f"Vanity URL:  {metadata['vanity_url']}")
print(f"Family safe: {metadata['is_family_safe']}")
print(f"Keywords:    {metadata.get('keywords') or 'none'}")
print(f"\nDescription:\n{metadata['description']}")
