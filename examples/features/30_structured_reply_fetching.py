#!/usr/bin/env python3
"""
Example: Fetching replies on demand

Fetches five top-level comments with their reply continuation tokens, then
fetches replies for up to three of those threads. Each thread costs at least
one extra request, so you only pay for the replies you ask for.
"""

import time

from yt_meta import YtMeta


def main():
    client = YtMeta()

    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

    print("Fetching replies on demand\n")

    print("Step 1: fetching comments with reply continuation tokens...")
    print(f"Video: {video_url}")
    print("Limit: 5 comments\n")

    comments_with_tokens = list(
        client.get_video_comments_with_reply_tokens(video_url, limit=5, sort_by="top")
    )

    print(f"Found {len(comments_with_tokens)} comments\n")

    comments_with_replies = []

    for i, comment in enumerate(comments_with_tokens, 1):
        print(f"Comment {i}:")
        print(f"  Author: {comment.get('author', 'Unknown')}")
        print(f"  Text: {comment.get('text', 'No text')[:100]}...")
        print(f"  Likes: {comment.get('like_count', 0)}")
        print(f"  Reply Count: {comment.get('reply_count', 0)}")

        if "reply_continuation_token" in comment:
            print("  Has replies (token available)")
            comments_with_replies.append(
                {"comment": comment, "token": comment["reply_continuation_token"]}
            )
        else:
            print("  No replies")

        print()

    # Only the first 3 threads, since each thread costs at least one request.
    total_replies = 0
    comments_with_replies = comments_with_replies[:3]
    if comments_with_replies:
        print(
            f"\nStep 2: fetching replies for {len(comments_with_replies)} comment(s) with replies...\n"
        )

        for j, item in enumerate(comments_with_replies, 1):
            comment = item["comment"]
            token = item["token"]

            print(f"Fetching replies for comment {j}:")
            print(f"  Original comment: {comment.get('text', 'No text')[:50]}...")
            print(f"  Reply count: {comment.get('reply_count', 0)}")
            print()

            replies = list(
                client.get_comment_replies(
                    video_url,
                    token,
                    limit=10,
                )
            )

            total_replies += len(replies)
            print(f"  Found {len(replies)} replies:")

            for k, reply in enumerate(replies, 1):
                print(f"    Reply {k}:")
                print(f"      Author: {reply.get('author', 'Unknown')}")
                print(f"      Text: {reply.get('text', 'No text')[:80]}...")
                print(f"      Likes: {reply.get('like_count', 0)}")
                print(f"      Is Reply: {reply.get('is_reply', False)}")
                print()

            # Space out requests to stay clear of YouTube's rate limits.
            if j < len(comments_with_replies):
                print("  (Pausing 1 second between reply fetches...)")
                time.sleep(1)
                print()
    else:
        print("No comments with replies found in this sample.")

    print("\nSummary")
    print(f"Total comments fetched: {len(comments_with_tokens)}")
    print(f"Threads expanded (at most 3): {len(comments_with_replies)}")

    print(f"Total replies fetched: {total_replies}")


if __name__ == "__main__":
    main()
