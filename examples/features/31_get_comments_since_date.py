#!/usr/bin/env python3
"""
Example: Comments since a date

Fetches comments posted in the last 30 days. since_date requires
sort_by="recent" (the default): comments then arrive newest first, and fetching
stops at the first comment older than the date, so the request count tracks
the number of recent comments rather than `limit`.
"""

from datetime import date, timedelta

try:
    from tqdm import tqdm
except ImportError:  # tqdm is optional; fall back to a plain-text counter
    class tqdm:  # noqa: N801 - stand-in for the optional dependency
        def __init__(self, total=None, desc="Progress", unit="", **kwargs):
            self.desc, self.n = desc, 0

        def update(self, n=1):
            self.n += n
            print(f"\r{self.desc}: {self.n}", end="", flush=True)

        def refresh(self):
            pass

        def close(self):
            print()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

from yt_meta import YtMeta


def main():
    client = YtMeta()

    # A video that still gets comments every day.
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    since_date = date.today() - timedelta(days=30)

    print("Fetching comments since a date")
    print(f"Video URL: {video_url}")
    print(f"Fetching comments posted on or after: {since_date.isoformat()}")
    print("Sorting by: 'recent' (required with since_date)\n")

    print("With sort_by='recent'")
    try:
        pbar = tqdm(desc="Fetching recent comments", unit=" comments")

        def progress_callback(count):
            pbar.update(count - pbar.n)

        comments_since = list(
            client.get_video_comments(
                video_url,
                sort_by="recent",
                since_date=since_date,
                limit=500,  # high on purpose: the date, not the limit, should stop the fetch
                progress_callback=progress_callback,
            )
        )
        pbar.close()

        print(
            f"\nFetched {len(comments_since)} comments posted since {since_date.isoformat()}.\n"
        )
        if comments_since:
            print("Newest comment:")
            if comments_since[0].get("publish_date"):
                print(f"  Date: {comments_since[0]['publish_date'].isoformat()}")
            print(f"  Author: {comments_since[0]['author']}")
            print(f"  Text: '{comments_since[0]['text'][:80]}...'")

            print("\nOldest comment fetched (should be on or after the target date):")
            if comments_since[-1].get("publish_date"):
                print(f"  Date: {comments_since[-1]['publish_date'].isoformat()}")
            print(f"  Author: {comments_since[-1]['author']}")
            print(f"  Text: '{comments_since[-1]['text'][:80]}...'")

    except Exception as e:
        print(f"Unexpected error: {e}")

    print("\n\nWith sort_by='top'")
    try:
        print("Calling with sort_by='top' and a since_date...")
        list(client.get_video_comments(video_url, sort_by="top", since_date=since_date))
    except ValueError as e:
        print(f"Caught expected error: {e}")
        print("since_date can't stop early on the top order, so the library refuses it.")

    print()
    print("Fetching stopped once comments got older than since_date,")
    print("even though limit was set higher.")


if __name__ == "__main__":
    main()
