import logging
import time
import json
from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# --- Configuration ---
# A video with a modest number of comments, as requested.
# URL: https://www.youtube.com/watch?v=feT7_wVmgv0
VIDEO_URL = "https://www.youtube.com/watch?v=feT7_wVmgv0"
MAX_COMMENTS = 15

# --- Script ---
def demonstrate_sorting(yt_meta: YtMeta, sort_order: str):
    """Fetches, times, and prints comments for a given sort order."""
    logger.info(f"--- Fetching up to {MAX_COMMENTS} comments sorted by: '{sort_order}' ---")
    start_time = time.time()

    comments_generator = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        sort_by=sort_order,
        limit=MAX_COMMENTS
    )

    comment_list = list(comments_generator)
    end_time = time.time()

    for i, comment in enumerate(comment_list):
        print(f"  Comment {i+1}:")
        print(f"    Author: {comment['author']}")
        print(f"    Likes: {comment['likes']}")
        print(f"    Published: {comment['published_time']}")
        clean_text = comment['text'][:80].replace('\\n', ' ')
        print(f"    Text: '{clean_text}...'")

    duration = end_time - start_time
    logger.info(f"Fetched {len(comment_list)} comments in {duration:.2f} seconds.")
    print("-" * 40)


if __name__ == "__main__":
    yt_meta = YtMeta()
    
    # Demonstrate fetching recent comments (chronological order)
    demonstrate_sorting(yt_meta, sort_order="recent")

    # Demonstrate fetching top comments (popularity order)
    demonstrate_sorting(yt_meta, sort_order="top") 