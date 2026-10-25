"""
Example: List a playlist's videos

get_playlist_videos yields a playlist's videos in playlist order, fetching
pages as you iterate.
"""

import itertools

from yt_meta import YtMeta

client = YtMeta()

# A Python tutorial playlist.
playlist_id = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"

print(f"Fetching videos from playlist: {playlist_id}\n")
videos_generator = client.get_playlist_videos(playlist_id=playlist_id)

print("First 10 videos:")
for i, video in enumerate(itertools.islice(videos_generator, 10), 1):
    title = video.get("title", "No Title")
    url = video.get("url", "N/A")

    print(f"{i}. {title}")
    print(f"   URL: {url}")
    print()
