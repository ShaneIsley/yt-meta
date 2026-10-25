"""
Example: List a channel's videos

get_channel_videos yields the channel's Videos tab, newest first, with the
fields the listing page carries. Pages are fetched as you iterate, so taking
the first 10 costs only the pages needed for those 10.
"""

import itertools

from yt_meta import YtMeta

client = YtMeta()

# The channel's home page or any of its tabs works.
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

print(f"Fetching videos from: {channel_url}\n")
videos_generator = client.get_channel_videos(channel_url)

print("First 10 videos:")
for i, video in enumerate(itertools.islice(videos_generator, 10), 1):
    video_id = video.get("video_id", "N/A")
    title = video.get("title", "No Title")
    views = video.get("view_count", "N/A")
    published = video.get("publish_date_text", "N/A")

    print(f"{i}. {title}")
    print(f"    ID: {video_id} | Views: {views} | Published: {published}")
    print()
