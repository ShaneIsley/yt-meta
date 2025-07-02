#!/usr/bin/env python3
"""
Example: Comment Deduplication with Multiple Sorting Methods

This example demonstrates how to fetch comments using both "top" and "recent" 
sorting methods, then combine and deduplicate them to get a comprehensive view
of a video's comments.

This technique helps ensure you get both the most popular comments (top) and 
the most recent activity (recent), without duplicates.
"""

import time

from yt_meta import YtMeta


def main():
    client = YtMeta()
    
    # Use a video with good comment activity
    video_url = "https://www.youtube.com/watch?v=hbRQ59R6-b8"
    limit_per_sort = 100
    
    print("=== Comment Deduplication with Multiple Sorting ===")
    print(f"Video: {video_url}")
    print(f"Fetching {limit_per_sort} comments with each sorting method")
    print()
    
    start_time = time.time()
    
    # Fetch comments using "top" sorting (most popular)
    print("📈 Fetching TOP comments (most popular)...")
    top_comments = list(client.get_video_comments(
        video_url,
        sort_by="top",
        limit=limit_per_sort
    ))
    
    # Fetch comments using "recent" sorting (chronological)
    print("🕒 Fetching RECENT comments (chronological)...")
    recent_comments = list(client.get_video_comments(
        video_url,
        sort_by="recent", 
        limit=limit_per_sort
    ))
    
    end_time = time.time()
    
    # Combine and deduplicate by comment ID
    print("\n🔄 Deduplicating comments...")
    all_comments_dict = {}
    
    # Add top comments first
    for comment in top_comments:
        all_comments_dict[comment['id']] = comment
    
    # Add recent comments (overwrites duplicates, keeping most recent data)
    for comment in recent_comments:
        all_comments_dict[comment['id']] = comment
    
    # Convert back to list
    unique_comments = list(all_comments_dict.values())
    
    # Analysis
    duplicates_found = len(top_comments) + len(recent_comments) - len(unique_comments)
    
    print(f"\n📊 DEDUPLICATION RESULTS:")
    print(f"TOP sorting: {len(top_comments)} comments")
    print(f"RECENT sorting: {len(recent_comments)} comments")
    print(f"Total fetched: {len(top_comments) + len(recent_comments)} comments")
    print(f"Duplicates found: {duplicates_found}")
    print(f"Unique comments: {len(unique_comments)}")
    print(f"Fetch time: {end_time - start_time:.1f} seconds")
    
    # Show some examples of the different perspectives
    print(f"\n🔥 TOP 3 MOST POPULAR COMMENTS:")
    top_sorted = sorted(top_comments, key=lambda x: x['like_count'], reverse=True)
    for i, comment in enumerate(top_sorted[:3], 1):
        print(f"{i}. {comment['author']} ({comment['like_count']} likes)")
        print(f"   {comment['text'][:80]}...")
        print()
    
    print(f"⏰ TOP 3 MOST RECENT COMMENTS:")
    # Recent comments are already in chronological order (newest first)
    for i, comment in enumerate(recent_comments[:3], 1):
        print(f"{i}. {comment['author']} ({comment['like_count']} likes)")
        print(f"   {comment['text'][:80]}...")
        print()
    
    # Show benefit of deduplication
    if duplicates_found > 0:
        print(f"✅ BENEFIT: By deduplicating, we saved {duplicates_found} redundant comments")
        print(f"   and got {len(unique_comments)} unique comments instead of {len(top_comments) + len(recent_comments)}.")
    else:
        print("📝 NOTE: No duplicates found - the two sorting methods returned completely different comments.")
    
    print(f"\n💡 TIP: This technique ensures you capture both viral comments")
    print(f"   (high engagement) and fresh activity (recent posts).")


if __name__ == "__main__":
    main() 