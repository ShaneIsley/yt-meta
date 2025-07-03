import itertools

from yt_meta import YtMeta
from yt_meta.date_utils import parse_relative_date_string

# Example: Find videos by filtering on their publish date.
# `publish_date` is a special filter. It can be "fast" for rough checks
# to stop pagination, but becomes a "slow" filter for precise, per-video
# checks, which requires fetching full metadata.

# Find videos published in 2012
# This uses the `gte` (greater than or equal to) and `lte` (less than or equal to) operators
# to create a date range.
if __name__ == "__main__":
    client = YtMeta()
    channel_url = "https://www.youtube.com/@samwitteveenai/videos"
    six_months_ago = parse_relative_date_string("6 months ago")
    filters = {"publish_date": {"gte": six_months_ago}}

    # The client will automatically set `fetch_full_metadata=True` to ensure
    # the date comparison is precise.
    print(f"Finding videos on {channel_url} published in the last 6 months...")
    videos = client.get_channel_videos(channel_url, filters=filters, max_videos=10)

    for video in itertools.islice(videos, 5):
        title = video.get("title", "N/A")
        p_date = video.get("publish_date", "N/A")
        print(f"- '{title}' (Published: {p_date})")
