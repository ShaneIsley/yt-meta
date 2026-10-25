#!/usr/bin/env python3
"""
Example: Merging top and recent comments

Fetches up to 100 comments with each of sort_by="top" and sort_by="recent",
then merges them by comment id. The result holds both the most-liked comments
and the latest ones, each once.
"""

import time

from yt_meta import YtMeta


def main():
    client = YtMeta()

    video_url = "https://www.youtube.com/watch?v=hbRQ59R6-b8"
    limit_per_sort = 100

    print("Merging top and recent comments")
    print(f"Video: {video_url}")
    print(f"Fetching {limit_per_sort} comments with each sort order")
    print()

    start_time = time.time()

    print("Fetching top comments...")
    top_comments = list(
        client.get_video_comments(video_url, sort_by="top", limit=limit_per_sort)
    )

    print("Fetching recent comments...")
    recent_comments = list(
        client.get_video_comments(video_url, sort_by="recent", limit=limit_per_sort)
    )

    end_time = time.time()

    print("\nMerging by comment id...")
    all_comments_dict = {}

    for comment in top_comments:
        all_comments_dict[comment["id"]] = comment

    # A comment in both lists keeps the copy from the recent fetch.
    for comment in recent_comments:
        all_comments_dict[comment["id"]] = comment

    unique_comments = list(all_comments_dict.values())

    duplicates_found = len(top_comments) + len(recent_comments) - len(unique_comments)

    print("\nResults")
    print(f"top: {len(top_comments)} comments")
    print(f"recent: {len(recent_comments)} comments")
    print(f"Total fetched: {len(top_comments) + len(recent_comments)} comments")
    print(f"Duplicates found: {duplicates_found}")
    print(f"Unique comments: {len(unique_comments)}")
    print(f"Fetch time: {end_time - start_time:.1f} seconds")

    print("\nThree most-liked comments")
    top_sorted = sorted(top_comments, key=lambda x: x["like_count"], reverse=True)
    for i, comment in enumerate(top_sorted[:3], 1):
        print(f"{i}. {comment['author']} ({comment['like_count']} likes)")
        print(f"   {comment['text'][:80]}...")
        print()

    print("Three newest comments")
    # The recent fetch is already newest first.
    for i, comment in enumerate(recent_comments[:3], 1):
        print(f"{i}. {comment['author']} ({comment['like_count']} likes)")
        print(f"   {comment['text'][:80]}...")
        print()

    if duplicates_found > 0:
        print(
            f"{duplicates_found} comments appeared in both lists; the merged list has"
        )
        print(
            f"   {len(unique_comments)} unique comments instead of {len(top_comments) + len(recent_comments)}."
        )
    else:
        print(
            "No duplicates: the two sort orders returned different comments."
        )


if __name__ == "__main__":
    main()
