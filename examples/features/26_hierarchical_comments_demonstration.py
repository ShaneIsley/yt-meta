"""
Example: Hierarchical Comment Organization

This example demonstrates how to organize YouTube comments into hierarchical 
structures by identifying parent-child relationships (replies).

This helps understand comment thread structure and conversation flow.
"""

import logging

from yt_meta import YtMeta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main():
    client = YtMeta()
    video_url = "https://www.youtube.com/watch?v=feT7_wVmgv0"
    
    try:
        logger.info(f"Fetching comments from: {video_url}")
        
        # Fetch comments that include replies
        comments = list(client.get_video_comments(
            video_url,
            sort_by="top",
            limit=30
        ))
        
        # Organize comments by hierarchy
        logger.info("Organizing comment hierarchy...")
        top_level_comments = []
        replies_by_parent = {}
        
        for comment in comments:
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
        total_replies = sum(len(replies) for replies in replies_by_parent.values())
        
        print(f"\n📊 HIERARCHY SUMMARY:")
        print(f"Total comments: {len(comments)}")
        print(f"Top-level comments: {len(top_level_comments)}")
        print(f"Reply threads: {len(replies_by_parent)}")
        print(f"Total replies: {total_replies}")
        
        # Show most active threads
        if replies_by_parent:
            print(f"\n💬 MOST ACTIVE THREADS:")
            # Sort threads by reply count
            sorted_threads = sorted(replies_by_parent.items(), 
                                  key=lambda x: len(x[1]), reverse=True)
            
            for i, (parent_id, replies) in enumerate(sorted_threads[:3], 1):
                # Find parent comment
                parent = next((c for c in top_level_comments if c['id'] == parent_id), None)
                if parent:
                    print(f"\n{i}. @{parent['author']} ({len(replies)} replies)")
                    print(f"   💬 {parent['text'][:70]}...")
                    print(f"   👍 {parent['like_count']} likes")
                    
                    # Show first reply
                    if replies:
                        first_reply = replies[0]
                        print(f"   ↳ @{first_reply['author']}: {first_reply['text'][:50]}...")
                        if len(replies) > 1:
                            print(f"   ↳ ... and {len(replies) - 1} more replies")
        
        # Educational summary
        print(f"\n✨ Hierarchical organization helps:")
        print(f"• Identify popular discussion topics")
        print(f"• Track conversation threads")
        print(f"• Find most engaging comments")
        print(f"• Understand community interactions")
        
    except Exception as e:
        logger.error(f"Failed to analyze comment hierarchy: {e}")
        print(f"❌ Error: Could not process comments from {video_url}")


if __name__ == "__main__":
    main()
