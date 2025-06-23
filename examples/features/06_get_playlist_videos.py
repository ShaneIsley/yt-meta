from yt_meta.client import YtMetaClient

client = YtMetaClient()

# Get all videos from a playlist
playlist_id = "PLS3XGZxi7cBVPQjjqZvZvokQduvf0bZVm"
videos = client.get_playlist_videos(playlist_id)

# Print the first 120 videos
for i, video in enumerate(videos):
    if i >= 120:
        break
    print(f"Title: {video['title']}")
    print(f"Video ID: {video['videoId']}")
    print(f"URL: {video['watchUrl']}")
    print("-" * 20) 