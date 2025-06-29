import logging
import time
from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# --- Configuration ---
VIDEO_URL = "https://www.youtube.com/watch?v=feT7_wVmgv0"
MAX_COMMENTS = 200  # High limit to ensure we get all available

def comprehensive_comment_fetch():
    """Demonstrates comprehensive comment fetching using multiple sorting methods."""
    logger.info(f"--- Comprehensive comment fetching from {VIDEO_URL} ---")
    start_time = time.time()

    yt_meta = YtMeta()
    
    # Fetch comments with both sorting methods
    print("Fetching comments with TOP sorting...")
    top_comments = list(yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        sort_by="top",
        limit=MAX_COMMENTS
    ))
    
    print("Fetching comments with RECENT sorting...")
    recent_comments = list(yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        sort_by="recent", 
        limit=MAX_COMMENTS
    ))
    
    end_time = time.time()

    # Combine and deduplicate comments
    all_comments_dict = {}
    
    # Add top comments
    for comment in top_comments:
        all_comments_dict[comment['id']] = comment
    
    # Add recent comments (will overwrite duplicates, which is fine)
    for comment in recent_comments:
        all_comments_dict[comment['id']] = comment
    
    all_comments = list(all_comments_dict.values())
    
    # Organize comments by hierarchy
    comments_by_id = {c['id']: c for c in all_comments}
    top_level_comments = []
    replies_by_parent = {}
    
    for comment in all_comments:
        if comment['parent_id']:
            # This is a reply
            parent_id = comment['parent_id']
            if parent_id not in replies_by_parent:
                replies_by_parent[parent_id] = []
            replies_by_parent[parent_id].append(comment)
        else:
            # This is a top-level comment
            top_level_comments.append(comment)

    # Display comprehensive results
    print("\n=== COMPREHENSIVE COMMENT ANALYSIS ===")
    print(f"Video URL: {VIDEO_URL}")
    print(f"Fetch time: {end_time - start_time:.2f} seconds")
    print("")
    print(f"TOP sorting yielded: {len(top_comments)} comments")
    print(f"RECENT sorting yielded: {len(recent_comments)} comments")
    print(f"Total unique comments: {len(all_comments)}")
    print(f"Top-level comments: {len(top_level_comments)}")
    print(f"Reply threads: {len(replies_by_parent)}")
    print(f"Total replies: {sum(len(replies) for replies in replies_by_parent.values())}")
    
    # Show reply distribution
    if replies_by_parent:
        print("\n=== REPLY THREAD ANALYSIS ===")
        for parent_id, replies in replies_by_parent.items():
            parent_comment = comments_by_id.get(parent_id)
            if parent_comment:
                print(f"Thread: {parent_comment['author']} ({len(replies)} replies)")
                print(f"  Parent: {parent_comment['text'][:60]}...")
                print(f"  Likes: {parent_comment['likes']} | Published: {parent_comment['published_time']}")
            else:
                print(f"Thread: Parent ID {parent_id} ({len(replies)} replies) - Parent not in fetched data")
            
            # Show replies
            for i, reply in enumerate(replies[:3]):  # Show first 3 replies
                print(f"  ↳ Reply {i+1}: {reply['author']}")
                print(f"    {reply['text'][:50]}...")
                print(f"    Likes: {reply['likes']} | Published: {reply['published_time']}")
            if len(replies) > 3:
                print(f"    ... and {len(replies) - 3} more replies")
            print()

    # Show sample of top-level comments sorted by likes
    print("\n=== TOP COMMENTS BY ENGAGEMENT ===")
    sorted_comments = sorted(top_level_comments, key=lambda x: x['likes'], reverse=True)
    for i, comment in enumerate(sorted_comments[:5]):
        print(f"#{i+1}: {comment['author']} ({comment['likes']} likes)")
        print(f"  {comment['text'][:80]}...")
        print(f"  Replies: {comment['reply_count']} | Published: {comment['published_time']}")
        print()

    # Show comparison with browser count
    print("=== BROWSER COMPARISON ===")
    print(f"Our fetch: {len(all_comments)} comments")
    print("Browser shows: ~36 comments (as reported)")
    print(f"Coverage: {len(all_comments)/36*100:.1f}% of browser-visible comments")
    
    if len(all_comments) < 36:
        print(f"\nNote: The {36 - len(all_comments)} missing comments might be:")
        print("- Loaded dynamically on scroll in the browser")
        print("- Behind additional pagination not accessible via this API")
        print("- Comments that require different API endpoints")
        print("- Comments filtered by YouTube's algorithm")

    logger.info(f"Comprehensive comment analysis completed in {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    comprehensive_comment_fetch() 