"""
Example: Video comments, top vs recent

Fetches the same video's comments with sort_by="top" and sort_by="recent"
(the default) and prints the first five of each.
"""

import logging

from yt_meta import YtMeta
from yt_meta.exceptions import VideoUnavailableError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

VIDEO_URL = "https://www.youtube.com/watch?v=B68agR-OeJM"
MAX_COMMENTS = 20


def fetch_comments_with_sorting(client: YtMeta, sort_by: str):
    """Print the first five comments in the given order and return how many were fetched."""
    try:
        logger.info(f"Fetching {MAX_COMMENTS} comments sorted by '{sort_by}'")

        comments = list(
            client.get_video_comments(
                youtube_url=VIDEO_URL, sort_by=sort_by, limit=MAX_COMMENTS
            )
        )

        print(f"\nComments sorted by '{sort_by}' ({len(comments)} found)")

        for i, comment in enumerate(comments[:5], 1):
            print(f"{i}. @{comment['author']}")
            print(f"   {comment['text'][:80]}...")
            print(
                f"   {comment['like_count']} likes | {comment['reply_count']} replies"
            )
            print(f"   Channel: {comment['author_channel_id']}")
            print()

        return len(comments)

    except VideoUnavailableError as e:
        logger.error(f"Video unavailable for {sort_by} comments: {e}")
        print(f"Cannot fetch {sort_by} comments: the video is unavailable")
        return 0

    except Exception as e:
        logger.error(f"Error fetching {sort_by} comments: {e}")
        print(f"Failed to fetch {sort_by} comments")
        return 0


def main():
    client = YtMeta()

    print("Video comments: top vs recent")
    print(f"Video: {VIDEO_URL}")

    top_count = fetch_comments_with_sorting(client, "top")
    recent_count = fetch_comments_with_sorting(client, "recent")

    print("Summary")
    print("- top: YouTube's ranking, usually the most-liked comments")
    print("- recent: newest first (the default)")
    print(f"- Fetched {top_count} top and {recent_count} recent comments")


if __name__ == "__main__":
    main()
