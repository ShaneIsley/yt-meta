#!/usr/bin/env python3
"""
Example: Pinned Comment Detection

This example demonstrates how to detect pinned comments in YouTube videos.
Pinned comments are typically posted by the video creator and appear at the
top of the comment section.
"""

import logging

from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    client = YtMeta()

    # "Me at the zoo" — its top comment is pinned ("Pinned by @jawed")
    video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

    try:
        logger.info(f"Fetching comments from: {video_url}")

        # Fetch comments — the pinned comment surfaces on the first page
        # of the 'top' sort
        comments = list(client.get_video_comments(video_url, sort_by="top", limit=15))

        # Separate pinned and regular comments
        pinned_comments = [c for c in comments if c.get("is_pinned", False)]
        regular_comments = [c for c in comments if not c.get("is_pinned", False)]

        logger.info(
            f"Found {len(pinned_comments)} pinned comment(s) and {len(regular_comments)} regular comment(s)"
        )

        # Display pinned comments
        if pinned_comments:
            print("\n📌 PINNED COMMENTS:")
            print("=" * 50)
            for i, comment in enumerate(pinned_comments, 1):
                print(f"{i}. @{comment['author']}")
                print(f"   💬 {comment['text'][:100]}...")
                print(
                    f"   👍 {comment['like_count']} likes | 💬 {comment['reply_count']} replies"
                )
                print(f"   📅 {comment['publish_date']}")
                print()
        else:
            print("\n📝 No pinned comments found in this video.")

        # Show a few regular comments for comparison
        if regular_comments:
            print("💭 REGULAR COMMENTS (first 3):")
            print("=" * 50)
            for i, comment in enumerate(regular_comments[:3], 1):
                print(f"{i}. @{comment['author']}")
                print(f"   💬 {comment['text'][:80]}...")
                print(f"   👍 {comment['like_count']} likes")
                print()

        # Educational summary
        print("✨ Why pinned comments matter:")
        print("• Highlight important announcements from creators")
        print("• Provide context or corrections to the video")
        print("• Show official responses to community feedback")
        print("• Often contain links or additional resources")

    except Exception as e:
        logger.error(f"Failed to fetch comments: {e}")
        print(f"❌ Error: Could not analyze comments from {video_url}")


if __name__ == "__main__":
    main()
