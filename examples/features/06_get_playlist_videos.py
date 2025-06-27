import itertools

from yt_meta import YtMeta

client = YtMeta()

playlist_id = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"  # Example playlist

print(f"Fetching videos from playlist: {playlist_id}\n")
videos_generator = client.get_playlist_videos(playlist_id=playlist_id)

print("--- First 10 Videos ---")
# We use itertools.islice to take just the first 10 videos.
for video in itertools.islice(videos_generator, 10):
    print(f"Title: {video['title']}")
    print(f"URL: {video['url']}")
    print("-" * 10)
