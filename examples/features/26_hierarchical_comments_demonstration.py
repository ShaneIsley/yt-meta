import logging
import time
from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# --- Configuration ---
VIDEO_URL = "https://www.youtube.com/watch?v=feT7_wVmgv0"
MAX_COMMENTS = 50  # Fetch more to get replies

def demonstrate_hierarchical_comments():
    """Demonstrates hierarchical comment fetching with parent-child relationships."""
    logger.info(f"--- Fetching hierarchical comments from {VIDEO_URL} ---")
    start_time = time.time()

    yt_meta = YtMeta()
    comments_generator = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        sort_by="top",
        limit=MAX_COMMENTS
    )

    all_comments = list(comments_generator)
    end_time = time.time()

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

    # Display results
    print("\n=== HIERARCHICAL COMMENT ANALYSIS ===")
    print(f"Total comments fetched: {len(all_comments)}")
    print(f"Top-level comments: {len(top_level_comments)}")
    print(f"Reply threads: {len(replies_by_parent)}")
    print(f"Total replies: {sum(len(replies) for replies in replies_by_parent.values())}")
    
    # Show reply distribution
    if replies_by_parent:
        print("\n=== REPLY DISTRIBUTION ===")
        for parent_id, replies in replies_by_parent.items():
            parent_comment = comments_by_id.get(parent_id)
            if parent_comment:
                print(f"Parent: {parent_comment['author']} ({len(replies)} replies)")
                print(f"  Text: {parent_comment['text'][:60]}...")
            else:
                print(f"Parent ID: {parent_id} ({len(replies)} replies) - Parent not in this batch")
            
            for i, reply in enumerate(replies[:3]):  # Show first 3 replies
                print(f"  ↳ Reply {i+1}: {reply['author']}")
                print(f"    Text: {reply['text'][:50]}...")
            if len(replies) > 3:
                print(f"    ... and {len(replies) - 3} more replies")
            print()

    # Show some top-level comments
    print("\n=== TOP-LEVEL COMMENTS ===")
    for i, comment in enumerate(top_level_comments[:5]):
        print(f"Comment {i+1}:")
        print(f"  ID: {comment['id']}")
        print(f"  Author: {comment['author']}")
        print(f"  Likes: {comment['likes']} | Replies: {comment['reply_count']}")
        print(f"  Text: {comment['text'][:80]}...")
        print()

    duration = end_time - start_time
    logger.info(f"Completed hierarchical comment analysis in {duration:.2f} seconds.")

if __name__ == "__main__":
    demonstrate_hierarchical_comments() 