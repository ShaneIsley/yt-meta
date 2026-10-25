"""
Example: Metadata for one video

Fetches a single video's page and prints the full metadata dict. A private
or deleted video is not an error: it comes back with status="unavailable".
VideoUnavailableError means the request itself failed.
"""

import logging
from pprint import pprint

from yt_meta import YtMeta
from yt_meta.exceptions import VideoUnavailableError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# One client can serve the whole application.
client = YtMeta()

# Any YouTube URL form or a bare 11-character id works.
video_url = (
    "https://www.youtube.com/watch?v=B68agR-OeJM"  # Metrik & Linguistics @ Hospitality
)

try:
    logger.info(f"Fetching metadata for video: {video_url}")
    video_meta = client.get_video_metadata(video_url)

    if video_meta:
        print("\nVideo metadata:")
        pprint(video_meta)
    else:
        print("The page had no player data for this video.")

except VideoUnavailableError as e:
    logger.error(f"Request failed: {e}")
    print(f"Error: could not fetch {video_url}")
    print(
        "   The request failed (network error, 404, or 429/5xx after retries)."
    )

except Exception as e:
    logger.error(f"Unexpected error fetching video metadata: {e}")
    print(f"Error: failed to read metadata from {video_url}")
