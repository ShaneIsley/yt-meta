"""
Example: Comment threads from reply tokens

Builds threads (a top-level comment plus its replies) by hand.
`get_video_comments` returns only top-level comments, because YouTube serves
replies through a continuation token per thread. The steps, also used in
example 30, are:

  1. `get_video_comments_with_reply_tokens(...)` returns top-level comments,
     each with a `reply_continuation_token` when it has replies.
  2. `get_comment_replies(video, token)` returns the replies for one thread,
     at one request per page of about 10 replies.

Example 27b does the same with `get_comment_threads`. (Before 0.8.0 this
example built threads from `parent_id`, which is always None on top-level
fetches, so it never found a reply.)
"""

import logging

from yt_meta import YtMeta

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    client = YtMeta()
    video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # Me at the zoo

    print(f"Fetching top comments from: {video_url}")
    top_level = list(
        client.get_video_comments_with_reply_tokens(
            video_url, sort_by="top", limit=10
        )
    )

    # Fetch replies only for the 3 threads with the most replies.
    threads = sorted(top_level, key=lambda c: c["reply_count"], reverse=True)
    hierarchy = {}
    for comment in threads[:3]:
        token = comment.get("reply_continuation_token")
        replies = (
            list(client.get_comment_replies(video_url, token, limit=5))
            if token
            else []
        )
        hierarchy[comment["id"]] = (comment, replies)

    total_replies = sum(c["reply_count"] for c in top_level)
    print("\nSummary")
    print(f"Top-level comments fetched: {len(top_level)}")
    print(f"Replies reported across them: {total_replies}")
    print(f"Threads expanded below: {len(hierarchy)}")

    print("\nMost active threads")
    for i, (comment, replies) in enumerate(hierarchy.values(), 1):
        print(f"\n{i}. @{comment['author']} ({comment['reply_count']} replies)")
        print(f"   {comment['text'][:70]}...")
        print(f"   {comment['like_count']} likes")
        for reply in replies:
            print(f"   ↳ @{reply['author']}: {reply['text'][:50]}...")
        if comment["reply_count"] > len(replies):
            print(f"   ↳ ... and {comment['reply_count'] - len(replies)} more replies")


if __name__ == "__main__":
    main()
