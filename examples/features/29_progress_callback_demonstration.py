"""
This example demonstrates how to use the progress_callback feature to monitor
the progress of long-running operations like fetching a large number of comments.
"""
import logging
import sys
from tqdm import tqdm
from yt_meta import YtMeta

# --- Configuration ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)
VIDEO_URL = "https://www.youtube.com/watch?v=B68agR-OeJM"
MAX_COMMENTS = 250

if __name__ == "__main__":
    yt_meta = YtMeta()

    # --- 1. Fetching without a progress callback ---
    # By default, no progress is shown. The library is silent.
    logger.info(f"--- Running without a progress callback (default behavior) ---")
    comments_generator_silent = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        limit=MAX_COMMENTS
    )
    # We consume the generator to actually fetch the comments
    comment_list_silent = list(comments_generator_silent)
    logger.info(f"Finished. Fetched {len(comment_list_silent)} comments silently.\n")


    # --- 2. Using a simple custom callback function ---
    # You can pass any function that accepts a single integer argument.
    def simple_progress_printer(count: int):
        # Using carriage return to print on the same line
        print(f"  ... Fetched {count} comments", end='\\r')

    logger.info(f"--- Running with a simple print callback ---")
    comments_generator_simple = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        limit=MAX_COMMENTS,
        progress_callback=simple_progress_printer
    )
    comment_list_simple = list(comments_generator_simple)
    print() # Newline after the progress printing is done
    logger.info(f"Finished. Fetched {len(comment_list_simple)} comments with a simple callback.\n")


    # --- 3. Using the `tqdm` library for a rich progress bar ---
    # For a better user experience, you can integrate with a library like tqdm.
    logger.info(f"--- Running with a tqdm progress bar ---")
    
    # Initialize tqdm progress bar
    with tqdm(total=MAX_COMMENTS, desc="Fetching Comments", unit="comment") as pbar:
        
        # The callback function will update the progress bar
        def tqdm_callback(count: int):
            # To update, we set the progress bar to the new total count
            pbar.n = count
            pbar.refresh()

        comments_generator_tqdm = yt_meta.get_video_comments(
            youtube_url=VIDEO_URL,
            limit=MAX_COMMENTS,
            progress_callback=tqdm_callback
        )
        comment_list_tqdm = list(comments_generator_tqdm)

    logger.info(f"Finished. Fetched {len(comment_list_tqdm)} comments with tqdm.") 