"""
Example: Progress callbacks

Fetches 250 comments three times: with no callback, with a callback that
prints a running count, and with a tqdm progress bar (a plain-text counter
stands in if tqdm is not installed).
"""

import logging
import sys

try:
    from tqdm import tqdm
except ImportError:  # tqdm is optional; fall back to a plain-text counter
    class tqdm:  # noqa: N801 - stand-in for the optional dependency
        def __init__(self, total=None, desc="Progress", unit="", **kwargs):
            self.desc, self.n = desc, 0

        def refresh(self):
            print(f"\r{self.desc}: {self.n}", end="", flush=True)

        def close(self):
            print()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

from yt_meta import YtMeta

logging.basicConfig(
    level=logging.INFO, stream=sys.stdout, format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)
VIDEO_URL = "https://www.youtube.com/watch?v=B68agR-OeJM"
MAX_COMMENTS = 250

if __name__ == "__main__":
    yt_meta = YtMeta()

    # Without a callback the library reports nothing while it fetches.
    logger.info("Running without a progress callback (the default)")
    comments_generator_silent = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL, limit=MAX_COMMENTS
    )
    # Nothing is fetched until the generator is consumed.
    comment_list_silent = list(comments_generator_silent)
    logger.info(f"Finished. Fetched {len(comment_list_silent)} comments silently.\n")

    # Any function that takes one int (the running count) works as a callback.
    def simple_progress_printer(count: int):
        print(f"  ... Fetched {count} comments", end="\r")

    logger.info("Running with a print callback")
    comments_generator_simple = yt_meta.get_video_comments(
        youtube_url=VIDEO_URL,
        limit=MAX_COMMENTS,
        progress_callback=simple_progress_printer,
    )
    comment_list_simple = list(comments_generator_simple)
    print()  # end the carriage-return line
    logger.info(
        f"Finished. Fetched {len(comment_list_simple)} comments with a print callback.\n"
    )

    logger.info("Running with a tqdm progress bar")

    with tqdm(total=MAX_COMMENTS, desc="Fetching Comments", unit="comment") as pbar:
        # The callback gets a running total, not an increment, so set n directly.
        def tqdm_callback(count: int):
            pbar.n = count
            pbar.refresh()

        comments_generator_tqdm = yt_meta.get_video_comments(
            youtube_url=VIDEO_URL, limit=MAX_COMMENTS, progress_callback=tqdm_callback
        )
        comment_list_tqdm = list(comments_generator_tqdm)

    logger.info(f"Finished. Fetched {len(comment_list_tqdm)} comments with tqdm.")
