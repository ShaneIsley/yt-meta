#!/usr/bin/env python3
"""
Example: Comment threads with get_comment_threads

Fetches 15 comment threads (a top-level comment plus up to 3 replies) and ranks
them by replies and likes. Each thread with replies costs one extra request.

`get_comment_threads` wraps the reply-token steps shown in example 26:
`get_video_comments` alone returns only top-level comments, because YouTube
serves replies through a continuation token per thread. (Before 0.8.0 this
example grouped by `parent_id`, which is always None on top-level fetches, so
it never found a reply.)
"""

from yt_meta import YtMeta


def main():
    client = YtMeta()
    video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # Me at the zoo

    print("Comment thread analysis")
    print(f"Video: {video_url}")
    print()

    print("Fetching comment threads...")
    # sort_by defaults to "recent"; "top" brings threads with replies to the front.
    threads = list(
        client.get_comment_threads(
            video_url, limit=15, replies_per_thread=3, sort_by="top"
        )
    )

    top_level = [comment for comment, _ in threads]
    total_reported_replies = sum(c["reply_count"] for c in top_level)

    print("\nSummary")
    print(f"Top-level comments: {len(top_level)}")
    print(f"Replies reported across them: {total_reported_replies}")

    print("\nMost active threads")
    by_activity = sorted(threads, key=lambda t: t[0]["reply_count"], reverse=True)
    for i, (parent, replies) in enumerate(by_activity[:3], 1):
        print(f"\n{i}. Thread by @{parent['author']} ({parent['reply_count']} replies)")
        print(f"   Parent: {parent['text'][:70]}...")
        print(f"   Likes: {parent['like_count']} | Date: {parent['publish_date']}")
        for j, reply in enumerate(replies[:2], 1):
            print(f"   - Reply {j}: @{reply['author']} - {reply['text'][:50]}...")
        if parent["reply_count"] > 2:
            print(f"   - ... and {parent['reply_count'] - 2} more replies")

    print("\nTop 5 comments by likes")
    by_likes = sorted(top_level, key=lambda c: c["like_count"], reverse=True)
    for i, comment in enumerate(by_likes[:5], 1):
        markers = []
        if comment["is_pinned"]:
            markers.append("pinned")
        if comment["is_hearted"]:
            markers.append("hearted")
        suffix = f" [{', '.join(markers)}]" if markers else ""
        print(f"\n{i}. @{comment['author']}{suffix}")
        print(f"   {comment['like_count']} likes | {comment['reply_count']} replies")
        print(f"   {comment['publish_date']}")


if __name__ == "__main__":
    main()
