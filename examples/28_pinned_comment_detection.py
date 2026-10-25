#!/usr/bin/env python3
"""
Example: Pinned comment detection

Fetches 15 comments and splits them on `is_pinned`. A pinned comment is one the
channel owner has fixed to the top of the comment section.
"""

import logging

from yt_meta import YtMeta

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    client = YtMeta()

    # "Me at the zoo": its top comment is pinned ("Pinned by @jawed").
    video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

    try:
        logger.info(f"Fetching comments from: {video_url}")

        # The pinned comment comes first under sort_by="top"; the default
        # "recent" order would bury it among newer comments.
        comments = list(client.get_video_comments(video_url, sort_by="top", limit=15))

        pinned_comments = [c for c in comments if c.get("is_pinned", False)]
        regular_comments = [c for c in comments if not c.get("is_pinned", False)]

        logger.info(
            f"Found {len(pinned_comments)} pinned comment(s) and {len(regular_comments)} regular comment(s)"
        )

        if pinned_comments:
            print("\nPinned comments")
            for i, comment in enumerate(pinned_comments, 1):
                print(f"{i}. @{comment['author']}")
                print(f"   {comment['text'][:100]}...")
                print(
                    f"   {comment['like_count']} likes | {comment['reply_count']} replies"
                )
                print(f"   {comment['publish_date']}")
                print()
        else:
            print("\nNo pinned comments found in this video.")

        if regular_comments:
            print("Regular comments (first 3)")
            for i, comment in enumerate(regular_comments[:3], 1):
                print(f"{i}. @{comment['author']}")
                print(f"   {comment['text'][:80]}...")
                print(f"   {comment['like_count']} likes")
                print()

    except Exception as e:
        logger.error(f"Failed to fetch comments: {e}")
        print(f"Error: could not fetch comments from {video_url}")


if __name__ == "__main__":
    main()
