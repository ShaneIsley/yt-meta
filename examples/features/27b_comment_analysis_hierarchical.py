#!/usr/bin/env python3
"""
Example: Hierarchical Comment Analysis

This example demonstrates how to analyze YouTube comments by organizing them
into parent-child relationships (replies) and analyzing engagement patterns.

This shows how to build a hierarchical view of comment threads and identify
the most engaging discussions.
"""

from yt_meta import YtMeta


def main():
    client = YtMeta()

    # Use a video with good comment discussions
    video_url = "https://www.youtube.com/watch?v=hbRQ59R6-b8"

    print("=== Hierarchical Comment Analysis ===")
    print(f"Video: {video_url}")
    print()

    # Fetch a reasonable number of comments for analysis
    print("📥 Fetching comments for analysis...")
    comments = list(client.get_video_comments(video_url, sort_by="top", limit=80))

    # Organize comments by hierarchy
    print("🏗️  Organizing comment hierarchy...")
    comments_by_id = {c["id"]: c for c in comments}
    top_level_comments = []
    replies_by_parent = {}

    for comment in comments:
        if comment["parent_id"]:
            # This is a reply
            parent_id = comment["parent_id"]
            if parent_id not in replies_by_parent:
                replies_by_parent[parent_id] = []
            replies_by_parent[parent_id].append(comment)
        else:
            # This is a top-level comment
            top_level_comments.append(comment)

    # Analysis results
    total_replies = sum(len(replies) for replies in replies_by_parent.values())

    print("\n📊 HIERARCHY ANALYSIS:")
    print(f"Total comments: {len(comments)}")
    print(f"Top-level comments: {len(top_level_comments)}")
    print(f"Reply threads: {len(replies_by_parent)}")
    print(f"Total replies: {total_replies}")

    # Show most engaging threads
    if replies_by_parent:
        print("\n💬 TOP 3 MOST ACTIVE THREADS:")
        thread_activity = []
        for parent_id, replies in replies_by_parent.items():
            parent_comment = comments_by_id.get(parent_id)
            if parent_comment:
                thread_activity.append((parent_comment, replies))

        # Sort by number of replies
        thread_activity.sort(key=lambda x: len(x[1]), reverse=True)

        for i, (parent, replies) in enumerate(thread_activity[:3], 1):
            print(f"\n{i}. Thread by @{parent['author']} ({len(replies)} replies)")
            print(f"   Parent: {parent['text'][:70]}...")
            print(f"   Likes: {parent['like_count']} | Date: {parent['publish_date']}")

            # Show first 2 replies
            for j, reply in enumerate(replies[:2], 1):
                print(f"   ↳ Reply {j}: @{reply['author']} - {reply['text'][:50]}...")

            if len(replies) > 2:
                print(f"   ↳ ... and {len(replies) - 2} more replies")

    # Show top comments by engagement
    print("\n🔥 TOP 5 COMMENTS BY ENGAGEMENT:")
    sorted_comments = sorted(
        top_level_comments, key=lambda x: x["like_count"], reverse=True
    )

    for i, comment in enumerate(sorted_comments[:5], 1):
        badges = (
            f" [{', '.join(comment['author_badges'])}]"
            if comment["author_badges"]
            else ""
        )
        print(f"\n{i}. @{comment['author']}{badges}")
        print(
            f"   💙 {comment['like_count']} likes | 💬 {comment['reply_count']} replies"
        )
        print(f"   📅 {comment['publish_date']}")
        print(f"   💭 {comment['text'][:100]}...")

    # Engagement insights
    if top_level_comments:
        avg_likes = sum(c["like_count"] for c in top_level_comments) / len(
            top_level_comments
        )
        avg_replies = sum(c["reply_count"] for c in top_level_comments) / len(
            top_level_comments
        )

        print("\n📈 ENGAGEMENT INSIGHTS:")
        print(f"Average likes per top-level comment: {avg_likes:.1f}")
        print(f"Average replies per top-level comment: {avg_replies:.1f}")

        # Find comments with disproportionate engagement
        high_engagement = [
            c for c in top_level_comments if c["like_count"] > avg_likes * 2
        ]
        print(f"Comments with 2x+ average likes: {len(high_engagement)}")

        threaded_comments = [c for c in top_level_comments if c["reply_count"] > 0]
        print(f"Comments that sparked discussions: {len(threaded_comments)}")

    print("\n✨ This analysis helps identify:")
    print("• Most engaging content creators")
    print("• Topics that generate discussion")
    print("• Comment threads worth following")
    print("• Community engagement patterns")


if __name__ == "__main__":
    main()
