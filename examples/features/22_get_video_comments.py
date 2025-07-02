"""
Example: Fetching video comments with different sorting methods.

This example demonstrates how to fetch comments using both "top" and "recent" 
sorting to see the difference in results.
"""
import logging

from yt_meta import YtMeta
from yt_meta.exceptions import VideoUnavailableError

# Configure logging  
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
VIDEO_URL = "https://www.youtube.com/watch?v=B68agR-OeJM"
MAX_COMMENTS = 20


def fetch_comments_with_sorting(client: YtMeta, sort_by: str):
    """Fetch and display comments with specified sorting."""
    try:
        logger.info(f"Fetching {MAX_COMMENTS} comments sorted by '{sort_by}'")
        
        comments = list(client.get_video_comments(
            youtube_url=VIDEO_URL,
            sort_by=sort_by,
            limit=MAX_COMMENTS
        ))
        
        print(f"\n📊 COMMENTS SORTED BY '{sort_by.upper()}' ({len(comments)} found):")
        print("=" * 60)
        
        for i, comment in enumerate(comments[:5], 1):  # Show first 5
            print(f"{i}. @{comment['author']}")
            print(f"   💬 {comment['text'][:80]}...")
            print(f"   👍 {comment['like_count']} likes | 💭 {comment['reply_count']} replies")
            print(f"   🔗 Channel: {comment['author_channel_id']}")
            print()
            
        return len(comments)
        
    except VideoUnavailableError as e:
        logger.error(f"Video unavailable for {sort_by} comments: {e}")
        print(f"❌ Cannot fetch {sort_by} comments: Video is not accessible")
        return 0
        
    except Exception as e:
        logger.error(f"Error fetching {sort_by} comments: {e}")
        print(f"❌ Failed to fetch {sort_by} comments from video")
        return 0


def main():
    client = YtMeta()
    
    print("=== Video Comments Sorting Demonstration ===")
    print(f"Video: {VIDEO_URL}")
    
    # Fetch comments with both sorting methods
    top_count = fetch_comments_with_sorting(client, "top")
    recent_count = fetch_comments_with_sorting(client, "recent")
    
    # Summary
    print("🎯 SORTING SUMMARY:")
    print("• TOP sorting shows most popular/engaging comments")
    print("• RECENT sorting shows newest comments first") 
    print(f"• Successfully fetched {top_count} top and {recent_count} recent comments")


if __name__ == "__main__":
    main()
