"""
Example: Comment Sorting Comparison

This example demonstrates the difference between YouTube's two comment 
sorting methods: "top" (most popular) and "recent" (chronological).

This helps understand how different sorting affects which comments you see.
"""

import logging

from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def fetch_and_display_comments(client: YtMeta, video_url: str, sort_by: str):
    """Fetch and display comments using the specified sorting method."""
    try:
        logger.info(f"Fetching comments sorted by: {sort_by}")
        
        comments = list(client.get_video_comments(
            video_url,
            sort_by=sort_by,
            limit=10
        ))
        
        print(f"\n📊 COMMENTS SORTED BY '{sort_by.upper()}':")
        print("=" * 50)
        
        for i, comment in enumerate(comments[:5], 1):
            print(f"{i}. @{comment['author']}")
            print(f"   💬 {comment['text'][:70].replace(chr(10), ' ')}...")
            print(f"   👍 {comment['like_count']} likes | 💭 {comment['reply_count']} replies")
            print(f"   📅 {comment['publish_date']}")
            print()
            
        return len(comments)
        
    except Exception as e:
        logger.error(f"Failed to fetch {sort_by} comments: {e}")
        return 0


def main():
    client = YtMeta()
    video_url = "https://www.youtube.com/watch?v=feT7_wVmgv0"
    
    print("=== Comment Sorting Comparison ===")
    print(f"Video: {video_url}")
    print("\nComparing 'top' vs 'recent' sorting methods...")
    
    # Fetch comments using different sorting methods
    recent_count = fetch_and_display_comments(client, video_url, "recent")
    top_count = fetch_and_display_comments(client, video_url, "top")
    
    # Educational summary
    print("🎯 SORTING DIFFERENCES:")
    print("• TOP sorting shows most popular/engaging comments first")
    print("• RECENT sorting shows newest comments first (chronological)")
    print("• Use TOP to find viral/important discussions")  
    print("• Use RECENT to see latest community activity")
    print(f"\nFetched {recent_count} recent and {top_count} top comments successfully!")


if __name__ == "__main__":
    main()
