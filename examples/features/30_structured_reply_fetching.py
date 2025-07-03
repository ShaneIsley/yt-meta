#!/usr/bin/env python3
"""
Example: Structured Reply Fetching

This example demonstrates how to use the new structured reply fetching feature
to get comments with reply continuation tokens, and then fetch replies for
specific comments on demand.

This approach allows for more efficient and structured handling of comment
threads, especially when you don't want to fetch all replies upfront.
"""

import time

from yt_meta import YtMeta


def main():
    client = YtMeta()

    # Use a video known to have comments with replies
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

    print("=== Structured Reply Fetching Example ===\n")

    # Step 1: Get comments with reply continuation tokens
    print("Step 1: Fetching comments with reply continuation tokens...")
    print(f"Video: {video_url}")
    print("Limit: 5 comments\n")

    comments_with_tokens = list(
        client.get_video_comments_with_reply_tokens(video_url, limit=50, sort_by="top")
    )

    print(f"Found {len(comments_with_tokens)} comments\n")

    # Display comments and identify which ones have replies
    comments_with_replies = []

    for i, comment in enumerate(comments_with_tokens, 1):
        print(f"Comment {i}:")
        print(f"  Author: {comment.get('author', 'Unknown')}")
        print(f"  Text: {comment.get('text', 'No text')[:100]}...")
        print(f"  Likes: {comment.get('like_count', 0)}")
        print(f"  Reply Count: {comment.get('reply_count', 0)}")

        if "reply_continuation_token" in comment:
            print("  ✅ Has replies (token available)")
            comments_with_replies.append(
                {"comment": comment, "token": comment["reply_continuation_token"]}
            )
        else:
            print("  ❌ No replies")

        print()

    # Step 2: Fetch replies for comments that have them
    if comments_with_replies:
        print(
            f"\nStep 2: Fetching replies for {len(comments_with_replies)} comment(s) with replies...\n"
        )

        for j, item in enumerate(comments_with_replies, 1):
            comment = item["comment"]
            token = item["token"]

            print(f"Fetching replies for comment {j}:")
            print(f"  Original comment: {comment.get('text', 'No text')[:50]}...")
            print(f"  Reply count: {comment.get('reply_count', 0)}")
            print()

            # Fetch replies for this specific comment
            replies = list(
                client.get_comment_replies(
                    video_url,
                    token,
                    limit=10,  # Limit replies per comment
                )
            )

            print(f"  Found {len(replies)} replies:")

            for k, reply in enumerate(replies, 1):
                print(f"    Reply {k}:")
                print(f"      Author: {reply.get('author', 'Unknown')}")
                print(f"      Text: {reply.get('text', 'No text')[:80]}...")
                print(f"      Likes: {reply.get('like_count', 0)}")
                print(f"      Is Reply: {reply.get('is_reply', False)}")
                print()

            # Add a small delay to be respectful to YouTube's servers
            if j < len(comments_with_replies):
                print("  (Pausing briefly between reply fetches...)")
                time.sleep(1)
                print()
    else:
        print("No comments with replies found in this sample.")

    print("\n=== Summary ===")
    print(f"Total comments fetched: {len(comments_with_tokens)}")
    print(f"Comments with replies: {len(comments_with_replies)}")

    total_replies = sum(
        len(list(client.get_comment_replies(video_url, item["token"], limit=10)))
        for item in comments_with_replies
    )
    print(f"Total replies fetched: {total_replies}")

    print("\n=== Benefits of Structured Reply Fetching ===")
    print("1. Fetch only the replies you need, when you need them")
    print("2. Better control over API rate limits and bandwidth")
    print("3. More efficient for applications that don't always need all replies")
    print("4. Cleaner separation between top-level comments and their replies")
    print("5. Enables building hierarchical comment UIs")


if __name__ == "__main__":
    main()
