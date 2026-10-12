"""
Example: filter channel videos by duration.

duration_seconds is a fast filter for channel videos: the listing
carries each video's length, so no extra request per video is needed.
(On get_channel_shorts it is slow: the Shorts listing has no duration.)
"""

import itertools

from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@ArjanCodes"

# Videos between 10 and 20 minutes long.
duration_filter = {"duration_seconds": {"gte": 10 * 60, "lte": 20 * 60}}

videos = client.get_channel_videos(channel_url, filters=duration_filter)

print(f"Videos on {channel_url} between 10 and 20 minutes long:")
for video in itertools.islice(videos, 5):
    minutes, seconds = divmod(video["duration_seconds"], 60)
    print(f"- {video['title']} ({minutes}:{seconds:02d})")
