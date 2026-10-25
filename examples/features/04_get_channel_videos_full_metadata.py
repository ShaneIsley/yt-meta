"""
Example: Channel videos with full metadata

fetch_full_metadata=True fetches each video's own page to add fields the
listing lacks (likes, category, exact publish date). It costs one extra
request per video.
"""

import itertools
import logging

from yt_meta import YtMeta

# INFO logging shows each video page request.
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

print(f"Fetching videos with full metadata from: {channel_url}\n")
videos_generator = client.get_channel_videos(
    channel_url,
    fetch_full_metadata=True,  # slow filters turn this on automatically
)

print("First 5 videos with full metadata:")
for video in itertools.islice(videos_generator, 5):
    video_id = video.get("video_id", "N/A")
    title = video.get("title", "No Title")
    views = video.get("view_count", "N/A")
    likes = video.get("like_count", "N/A")
    category = video.get("category", "N/A")

    print(f"- Title: {title}")
    print(
        f"  Info: (ID: {video_id}) - Views: {views:,} - Likes: {likes:,} - Category: {category}\n"
    )

print("Full metadata costs one request per video, so it is slower than the listing alone.")
