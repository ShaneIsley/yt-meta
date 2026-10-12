"""
Example: filter channel videos with a publish_date condition.

publish_date is a fast filter for channel videos. It compares the
listing's approximate date, parsed from relative text such as
"3 weeks ago", so no extra request per video is needed, and pagination
stops once videos are older than the start of the window.

Pass fetch_full_metadata=True when you need exact upload dates; the
approximate date is then only a coarse pre-filter.
"""

import itertools

from yt_meta import YtMeta, parse_relative_date_string

client = YtMeta()
channel_url = "https://www.youtube.com/@ArjanCodes"

six_months_ago = parse_relative_date_string("6 months ago")
filters = {"publish_date": {"gte": six_months_ago}}

print(f"Videos on {channel_url} published in the last 6 months:")
videos = client.get_channel_videos(channel_url, filters=filters)
for video in itertools.islice(videos, 5):
    print(
        f"- {video['title']} "
        f"({video['publish_date_text']}, ~{video['publish_date']:%Y-%m-%d})"
    )
