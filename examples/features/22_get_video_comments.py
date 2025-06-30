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

    logger.info(f"Fetching up to {MAX_COMMENTS} comments for video: {VIDEO_URL} (sorted by 'top')")
    comments_generator_top = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        sort_by='top',
        limit=MAX_COMMENTS
    )

    comment_count = 0
    for comment in comments_generator_top:
        comment_count += 1
        print(f"Comment {comment_count}:")
        print(f"  Author: {comment['author']} (Channel: {comment['author_channel_id']})")
        print(f"  Text: '{comment['text'][:100]}...'")
        print(f"  Likes: {comment['likes']} | Replies: {comment['reply_count']} | Is a Reply: {comment['is_reply']}")
        print("-" * 20)

    logger.info(f"Finished fetching {comment_count} 'top' comments.")
    print("\n" + "="*40 + "\n")

    logger.info(f"Fetching up to {MAX_COMMENTS} comments for video: {VIDEO_URL} (sorted by 'recent')")
    comments_generator_recent = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        sort_by='recent',
        limit=MAX_COMMENTS
    )

    comment_count = 0
    for comment in comments_generator_recent:
        comment_count += 1
        print(f"Comment {comment_count}:")
        print(f"  Author: {comment['author']} (Channel: {comment['author_channel_id']})")
        print(f"  Text: '{comment['text'][:100]}...'")
        print(f"  Likes: {comment['likes']} | Replies: {comment['reply_count']} | Is a Reply: {comment['is_reply']}")
        print("-" * 20)

    logger.info(f"Finished fetching {comment_count} 'recent' comments.")
