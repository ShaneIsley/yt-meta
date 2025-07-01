#!/usr/bin/env python3
"""
Example: Fetching Comments Since a Specific Date

This example demonstrates how to efficiently fetch comments that have been
posted since a specific date.

The library optimizes this by requiring comments to be sorted by 'recent'.
It then stops fetching new pages of comments as soon as it finds a comment
older than the specified date, minimizing API calls and processing time.
"""
from datetime import date, timedelta

from tqdm import tqdm
from yt_meta import YtMeta

def main():
    client = YtMeta()

    # A video with a long comment history is ideal for this demonstration.
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # A classic

    # Calculate a date 30 days ago
    since_date = date.today() - timedelta(days=30)

    print("=" * 60)
    print(" Fetching Comments Since a Specific Date")
    print("=" * 60)
    print(f"Video URL: {video_url}")
    print(f"Fetching comments posted on or after: {since_date.isoformat()}")
    print(f"Sorting by: 'recent' (required for this feature)\n")

    # --- Test Case 1: Correct Usage ---
    print("--- Correct Usage: sort_by='recent' ---")
    try:
        # Use a progress bar to see how many comments are fetched
        pbar = tqdm(desc="Fetching recent comments", unit=" comments")
        
        def progress_callback(count):
            pbar.update(count - pbar.n)

        comments_since = list(client.get_video_comments(
            video_url,
            sort_by='recent',
            since_date=since_date,
            limit=500, # Set a high limit to show that the date filter stops it
            progress_callback=progress_callback
        ))
        pbar.close()

        print(f"\nSuccessfully fetched {len(comments_since)} comments posted since {since_date.isoformat()}.\n")
        if comments_since:
            print("Most recent comment found:")
            if 'publish_date' in comments_since[0]:
                print(f"  Date: {comments_since[0]['publish_date'].isoformat()}")
            print(f"  Author: {comments_since[0]['author']}")
            print(f"  Text: '{comments_since[0]['text'][:80]}...'")
            
            print("\nOldest comment fetched (should be on or after the target date):")
            if 'publish_date' in comments_since[-1]:
                print(f"  Date: {comments_since[-1]['publish_date'].isoformat()}")
            print(f"  Author: {comments_since[-1]['author']}")
            print(f"  Text: '{comments_since[-1]['text'][:80]}...'")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    # --- Test Case 2: Incorrect Usage ---
    print("\n\n--- Incorrect Usage: sort_by='top' ---")
    try:
        print("Attempting to fetch with sort_by='top' and a since_date...")
        list(client.get_video_comments(
            video_url,
            sort_by='top',
            since_date=since_date
        ))
    except ValueError as e:
        print(f"Successfully caught expected error: {e}")
        print("This confirms the library prevents inefficient filtering.")

    print("\n" + "=" * 60)
    print("This example shows how the library stops fetching comments once")
    print("the date limit is reached, even if the 'limit' is much higher.")
    print("This saves significant time and network resources.")
    print("=" * 60)


if __name__ == "__main__":
    main() 