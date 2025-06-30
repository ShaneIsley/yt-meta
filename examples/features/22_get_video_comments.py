"""
Example: Fetching and filtering video comments.
"""
import logging

from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# --- Configuration ---
VIDEO_URL = "https://www.youtube.com/watch?v=B68agR-OeJM"
MAX_COMMENTS = 50

# --- Script ---
if __name__ == "__main__":
    yt_meta = YtMeta()

    logger.info(f"Fetching up to {MAX_COMMENTS} comments for video: {VIDEO_URL}")

    # The sort_by parameter is no longer supported in this implementation
    comments_generator = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        limit=MAX_COMMENTS
    )

    comment_count = 0
    for comment in comments_generator:
        comment_count += 1
        print(f"Comment {comment_count}:")
        print(f"  Author: {comment['author']}")
        print(f"  Text: '{comment['text'][:100]}...'") # Truncate for readability
        print(f"  Likes: {comment['likes']}")
        print("-" * 20)

    logger.info(f"Finished fetching {comment_count} comments.")
