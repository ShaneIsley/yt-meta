from yt_meta import YtMeta

# Initialize the client
yt_meta = YtMeta()

# The channel URL for @bashbunni
channel_url = "https://www.youtube.com/@bashbunni"

print(f"Fetching shorts for {channel_url} with full metadata (Slow Path)...")

# Use the get_channel_shorts method with `fetch_full_metadata=True`.
# This triggers the "slow path" to get all details for each short.
# We can also use "slow" filters, like `like_count`.
try:
    shorts_generator = yt_meta.get_channel_shorts(
        channel_url,
        fetch_full_metadata=True,
        filters={"like_count": {"gt": 100}},  # Example of a slow filter
        max_videos=5,
    )

    for i, short in enumerate(shorts_generator):
        print(f"  - Short {i + 1}:")
        print(f"    - Title: {short['title']}")
        print(f"    - Video ID: {short['video_id']}")
        print(f"    - View Count: {short.get('view_count', 'N/A')}")
        print(f"    - URL: {short['url']}")
        # --- Slow path fields ---
        print(f"    - Publish Date: {short.get('publish_date', 'N/A')}")
        print(f"    - Like Count: {short.get('like_count', 'N/A')}")
        print(f"    - Category: {short.get('category', 'N/A')}")
        print(f"    - Duration (s): {short.get('duration_seconds', 'N/A')}")
        print("-" * 20)

except Exception as e:
    print(f"An error occurred: {e}")
