#!/usr/bin/env python3
"""
Pinned Comment Detection Example

This example demonstrates how to detect pinned comments in YouTube videos.
Pinned comments are typically posted by the video creator and appear at the
top of the comment section.

The video used in this example has a pinned comment from the creator.
"""

import time

from yt_meta import YtMeta


def main():
    yt_meta = YtMeta()

    # This video has a pinned comment by the creator
    video_url = "https://www.youtube.com/watch?v=ZMs2xCmosvI"

    print("🔍 Analyzing YouTube video for pinned comments...")
    print(f"📺 Video: {video_url}")
    print()

    # Fetch comments with a reasonable limit
    print("💬 Fetching comments...")
    start_time = time.time()
    comments = list(yt_meta.get_video_comments(video_url, limit=20))
    end_time = time.time()

    print(f"✅ Fetched {len(comments)} comments in {end_time - start_time:.2f}s")
    print()

    # Separate pinned and regular comments
    pinned_comments = [c for c in comments if c.get('is_pinned', False)]
    regular_comments = [c for c in comments if not c.get('is_pinned', False)]

    print(f"📌 Found {len(pinned_comments)} pinned comment(s)")
    print(f"💭 Found {len(regular_comments)} regular comment(s)")
    print()

    # Display pinned comments
    if pinned_comments:
        print("📌 PINNED COMMENTS:")
        print("=" * 60)
        for i, comment in enumerate(pinned_comments, 1):
            print(f"Pinned Comment #{i}:")
            print(f"👤 Author: {comment['author']}")
            print(f"💬 Text: {comment['text'][:100]}{'...' if len(comment['text']) > 100 else ''}")
            print(f"👍 Likes: {comment['likes']}")
            print(f"🕒 Published: {comment['published_time']}")
            print(f"🆔 ID: {comment['id']}")
            print()

    # Display top regular comments
    print("💭 TOP REGULAR COMMENTS:")
    print("=" * 60)
    for i, comment in enumerate(regular_comments[:5], 1):
        print(f"Comment #{i}:")
        print(f"👤 Author: {comment['author']}")
        print(f"💬 Text: {comment['text'][:100]}{'...' if len(comment['text']) > 100 else ''}")
        print(f"👍 Likes: {comment['likes']}")
        print(f"💬 Replies: {comment['reply_count']}")
        print(f"🕒 Published: {comment['published_time']}")
        print()

    # Summary statistics
    print("📊 SUMMARY:")
    print("=" * 60)
    print(f"Total comments analyzed: {len(comments)}")
    print(f"Pinned comments: {len(pinned_comments)}")
    print(f"Regular comments: {len(regular_comments)}")

    if pinned_comments:
        avg_pinned_likes = sum(c['likes'] for c in pinned_comments) / len(pinned_comments)
        print(f"Average likes on pinned comments: {avg_pinned_likes:.1f}")

    if regular_comments:
        avg_regular_likes = sum(c['likes'] for c in regular_comments) / len(regular_comments)
        print(f"Average likes on regular comments: {avg_regular_likes:.1f}")

    print()
    print("✨ Pinned comment detection helps identify:")
    print("  • Creator announcements and important updates")
    print("  • Official responses to community feedback")
    print("  • Key information highlighted by the content creator")
    print("  • Community guidelines or video corrections")

if __name__ == "__main__":
    main()
