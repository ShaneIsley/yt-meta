"""
Example: Fetching and filtering video comments.
"""
import itertools
import logging

from yt_meta import YtMeta
from yt_meta.client import SORT_BY_POPULAR

# Configure logging to see the library's output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# The URL of the video we want to get comments from
video_id = "KUCZe1xBKFM"
video_url = f"https://www.youtube.com/watch?v={video_id}"

# Initialize the client
client = YtMeta()

# --- Example: Get up to 5 popular comments with more than 100 likes ---
print(f"Fetching up to 5 popular comments for video with over 100 likes: {video_url}")
print("-" * 30)

# The 'limit' parameter acts as a maximum cap on the number of comments to return.
# The 'filters' are applied *before* a comment is counted towards the limit.
# Therefore, you may get fewer than the limit if not enough comments match the filter.
filters = {"like_count": {"gt": 100}}

comments_generator = client.get_video_comments(
    video_url,
    sort_by=SORT_BY_POPULAR,
    filters=filters,
    limit=5
)

comments_found = 0
for comment in comments_generator:
    comments_found += 1
    author = comment.get('author')
    likes = comment.get('like_count')
    text = comment.get('text', '').replace('\n', ' ')
    published = comment.get('published_text')
    
    print(f"Author: {author} ({likes} likes, {published})")
    print(f"Comment: {text}")
    
    if comment.get('is_by_owner'):
        print("[COMMENT BY VIDEO CREATOR]")
    if comment.get('is_hearted_by_owner'):
        print("[HEARTED BY CREATOR]")
    print("-" * 30)

print(f"\nFound {comments_found} comments matching the criteria.") 