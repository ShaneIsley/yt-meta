from yt_meta import YtMeta

# Initialize the client
yt_meta = YtMeta()

# The channel URL for @bashbunni
channel_url = "https://www.youtube.com/@bashbunni"

print(f"Fetching shorts for {channel_url} (Fast Path)...")

# Use the get_channel_shorts method.
# By default, this is the "fast path" and only fetches data available on the main shorts page.
try:
    shorts_generator = yt_meta.get_channel_shorts(channel_url, max_videos=5)
    for i, short in enumerate(shorts_generator):
        print(f"  - Short {i+1}:")
        print(f"    - Title: {short['title']}")
        print(f"    - Video ID: {short['video_id']}")
        print(f"    - View Count: {short.get('view_count', 'N/A')}")
        print(f"    - URL: {short['url']}")
        print("-" * 20)

except Exception as e:
    print(f"An error occurred: {e}") 