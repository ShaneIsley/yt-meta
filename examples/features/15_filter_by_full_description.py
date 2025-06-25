import itertools
from yt_meta import YtMetaClient

# Example: Find videos by filtering on their full description text.
# This is a "slow" filter because the full description requires fetching
# full metadata for each video.

client = YtMetaClient()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Find videos where the full description contains "LangChain". This is useful
# for finding videos that mention a specific technology or link.
filters = {
    "full_description": {"contains": "LangChain"}
}

# The client will automatically set `fetch_full_metadata=True`
print(f"Finding videos on {channel_url} with 'LangChain' in the full description...")
videos = client.get_channel_videos(channel_url, filters=filters)

for video in itertools.islice(videos, 5):
    title = video.get('title', 'N/A')
    # Fetching a snippet of the description to show it matched
    description_snippet = " ".join(video.get('full_description', '').split()[:20])
    print(f"- '{title}'\n  Description snippet: '{description_snippet}...'\n") 