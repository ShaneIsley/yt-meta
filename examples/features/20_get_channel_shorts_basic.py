"""
Example: Basic Channel Shorts Fetching

This example demonstrates how to fetch YouTube Shorts from a channel using
the basic/fast method that only requires data from the main shorts page.

Key concepts:
• Channel shorts fetching (fast path)
• Basic shorts metadata access
• Generator-based iteration
• Error handling for shorts content
"""

from yt_meta import YtMeta

# --- 1. Initialize the client ---
client = YtMeta()

# --- 2. Define the channel URL ---
# Using @bashbunni which has good shorts content for testing
channel_url = "https://www.youtube.com/@bashbunni"

# --- 3. Fetch shorts (fast path) ---
# By default, this uses the "fast path" with data from the main shorts page
print(f"Fetching shorts from: {channel_url}")
print("Using fast path (basic metadata only)\n")

try:
    shorts_generator = client.get_channel_shorts(channel_url, max_videos=5)

    # --- 4. Display results ---
    print("--- Channel Shorts (First 5) ---")
    for i, short in enumerate(shorts_generator, 1):
        title = short.get("title", "No Title")
        video_id = short.get("video_id", "N/A")
        views = short.get("view_count", "N/A")
        url = short.get("url", "N/A")

        print(f"{i}. {title}")
        print(f"    Video ID: {video_id}")
        print(f"    Views: {views}")
        print(f"    URL: {url}")
        print()

    print("✅ Channel shorts fetching complete!")

except Exception as e:
    print(f"❌ Error occurred while fetching shorts: {e}")
    print("   Please check the channel URL and try again")
