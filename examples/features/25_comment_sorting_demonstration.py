"""
Example: Comment sorting comparison

Prints the first five comments of a video under each of YouTube's two orders:
"recent" (newest first, the default) and "top" (YouTube's ranking).
"""

import logging

from yt_meta import YtMeta

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def fetch_and_display_comments(client: YtMeta, video_url: str, sort_by: str):
    """Print the first five comments in the given order and return how many were fetched."""
    try:
        logger.info(f"Fetching comments sorted by: {sort_by}")

        comments = list(client.get_video_comments(video_url, sort_by=sort_by, limit=10))

        print(f"\nComments sorted by '{sort_by}'")

        for i, comment in enumerate(comments[:5], 1):
            print(f"{i}. @{comment['author']}")
            print(f"   {comment['text'][:70].replace(chr(10), ' ')}...")
            print(
                f"   {comment['like_count']} likes | {comment['reply_count']} replies"
            )
            print(f"   {comment['publish_date']}")
            print()

        return len(comments)

    except Exception as e:
        logger.error(f"Failed to fetch {sort_by} comments: {e}")
        return 0


def main():
    client = YtMeta()
    video_url = "https://www.youtube.com/watch?v=feT7_wVmgv0"

    print("Comment sorting comparison")
    print(f"Video: {video_url}")
    print("\nComparing 'top' and 'recent' sorting...")

    recent_count = fetch_and_display_comments(client, video_url, "recent")
    top_count = fetch_and_display_comments(client, video_url, "top")

    print("How the two orders differ")
    print("- top: YouTube's ranking, usually the most-liked comments first")
    print("- recent: newest first")
    print("- Use top to find the discussions most viewers see")
    print("- Use recent to see the latest activity")
    print(f"\nFetched {recent_count} recent and {top_count} top comments.")


if __name__ == "__main__":
    main()
