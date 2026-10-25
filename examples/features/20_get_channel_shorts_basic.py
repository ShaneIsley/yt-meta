"""
Example: Channel Shorts

Lists the first five Shorts on a channel's Shorts tab. Only title, video id,
view count and URL come from the listing; this costs no extra request per Short.
"""

from yt_meta import YtMeta

client = YtMeta()

# @bashbunni posts Shorts regularly.
channel_url = "https://www.youtube.com/@bashbunni"

print(f"Fetching shorts from: {channel_url}")
print("Listing fields only, no per-Short requests\n")

try:
    shorts_generator = client.get_channel_shorts(channel_url, max_videos=5)

    print("Channel Shorts (first 5)")
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

    print("Done.")

except Exception as e:
    print(f"Error while fetching shorts: {e}")
    print("   Check the channel URL and try again.")
