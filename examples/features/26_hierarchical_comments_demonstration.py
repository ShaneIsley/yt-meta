"""
Example: Hierarchical Comment Organization

This example demonstrates how to organize YouTube comments into
hierarchical threads (a top-level comment plus its replies).

`get_video_comments` returns only TOP-LEVEL comments — YouTube serves
replies through per-thread continuation tokens, not inline. The correct
workflow (also shown in example 30) is:

  1. `get_video_comments_with_reply_tokens(...)` — top-level comments,
     each carrying a `reply_continuation_token` when it has replies;
  2. `get_comment_replies(video, token)` — the replies for one thread.

(Before 0.8.0 this example built the hierarchy from `parent_id`, which
is always None on top-level fetches — it demonstrated nothing.)
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

    # Build the hierarchy: fetch replies for the 3 most-replied threads.
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
    print("\n📊 HIERARCHY SUMMARY:")
    print(f"Top-level comments fetched: {len(top_level)}")
    print(f"Replies reported across them: {total_replies}")
    print(f"Threads expanded below: {len(hierarchy)}")

    print("\n💬 MOST ACTIVE THREADS:")
    for i, (comment, replies) in enumerate(hierarchy.values(), 1):
        print(f"\n{i}. @{comment['author']} ({comment['reply_count']} replies)")
        print(f"   💬 {comment['text'][:70]}...")
        print(f"   👍 {comment['like_count']} likes")
        for reply in replies:
            print(f"   ↳ @{reply['author']}: {reply['text'][:50]}...")
        if comment["reply_count"] > len(replies):
            print(f"   ↳ ... and {comment['reply_count'] - len(replies)} more replies")

    print("\n✨ Hierarchical organization helps:")
    print("• Identify popular discussion topics")
    print("• Track conversation threads")
    print("• Find most engaging comments")
    print("• Understand community interactions")


if __name__ == "__main__":
    main()
