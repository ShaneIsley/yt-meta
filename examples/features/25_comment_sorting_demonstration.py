import logging
import time
from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# --- Configuration ---
# A video with a modest number of comments, as requested.
# URL: https://www.youtube.com/watch?v=feT7_wVmgv0
VIDEO_URL = "https://www.youtube.com/watch?v=feT7_wVmgv0"
MAX_COMMENTS = 15

# --- Script ---
def demonstrate_sorting(yt_meta: YtMeta, sort_order: str):
    """Fetches, times, and prints comments for a given sort order."""
    logger.info(f"--- Fetching up to {MAX_COMMENTS} comments sorted by: '{sort_order}' ---")
    start_time = time.time()

    comments_generator = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        sort_by=sort_order,
        limit=MAX_COMMENTS
    )

    comment_list = list(comments_generator)
    end_time = time.time()

    # Group comments by parent-child relationships
    comments_by_id = {c['id']: c for c in comment_list}
    top_level_comments = []
    
    for comment in comment_list:
        if comment['parent_id']:
            # This is a reply - add it to parent's replies list
            parent = comments_by_id.get(comment['parent_id'])
            if parent:
                parent.setdefault('replies', []).append(comment)
        else:
            # This is a top-level comment
            top_level_comments.append(comment)
    
    # Display hierarchical structure
    for i, comment in enumerate(top_level_comments):
        print(f"Comment {i+1}:")
        print(f"  ID: {comment['id']}")
        print(f"  Author: {comment['author']} (Channel ID: {comment['author_channel_id']})")
        print(f"  Avatar: {comment['author_avatar_url']}")
        print(f"  Likes: {comment['likes']} | Replies: {comment['reply_count']}")
        print(f"  Published: {comment['published_time']}")
        clean_text = comment['text'][:80].replace('\\n', ' ')
        print(f"  Text: '{clean_text}...'")
        
        # Show replies if any
        if 'replies' in comment:
            for r_idx, reply in enumerate(comment['replies']):
                print(f"    ↳ Reply {r_idx+1}:")
                print(f"      ID: {reply['id']} (Parent: {reply['parent_id']})")
                print(f"      Author: {reply['author']}")
                print(f"      Likes: {reply['likes']}")
                reply_text = reply['text'][:60].replace('\\n', ' ')
                print(f"      Text: '{reply_text}...'")
        print("-" * 40)

    duration = end_time - start_time
    total_replies = sum(len(c.get('replies', [])) for c in top_level_comments)
    logger.info(f"Fetched {len(top_level_comments)} top-level comments with {total_replies} replies ({len(comment_list)} total) in {duration:.2f} seconds.")
    print("-" * 40)


if __name__ == "__main__":
    yt_meta = YtMeta()
    
    # Demonstrate fetching recent comments (chronological order)
    demonstrate_sorting(yt_meta, sort_order="recent")

    # Demonstrate fetching top comments (popularity order)
    demonstrate_sorting(yt_meta, sort_order="top") 