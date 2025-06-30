#!/usr/bin/env python3
"""
Script to dump comment data from YouTube API responses for analysis.
This will save every API response we receive so we can inspect the data structures.
"""

import json
import os
import time
from datetime import datetime


def save_response(data, filename_prefix, output_dir="comment_responses"):
    """Save API response with timestamp"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved API response to: {filepath}")
    return filepath

def main():
    # Use the same video that works in our demo
    video_url = "https://www.youtube.com/watch?v=feT7_wVmgv0"

    print(f"Fetching comment data from: {video_url}")

    # Access the comment fetcher through the private attribute
    from yt_meta.comment_fetcher import CommentFetcher
    fetcher = CommentFetcher()

    # Get the initial HTML and extract data using httpx directly
    response = fetcher._client.get(video_url)
    response.raise_for_status()
    html_content = response.text

    initial_data = fetcher._extract_initial_data(html_content)

    # Save initial data
    save_response(initial_data, "initial_data")

    # Get API key and context for continuation requests
    api_key, context = fetcher._find_api_key_and_context(html_content)

    # Find continuation token
    continuation_token = fetcher._find_continuation_token(initial_data)

    if continuation_token:
        print(f"Found continuation token: {continuation_token[:50]}...")

        # Make continuation request using the same method as CommentFetcher
        payload = {
            "context": context,
            "continuation": continuation_token
        }
        response = fetcher._client.post(f"https://www.youtube.com/youtubei/v1/next?key={api_key}", json=payload)
        response.raise_for_status()
        continuation_data = response.json()

        # Save continuation data
        continuation_file = save_response(continuation_data, "continuation_data")

        # Make a few more continuation requests to get different response types
        for i in range(5):  # Increased from 3 to 5
            next_token = fetcher._find_continuation_token(continuation_data)
            if next_token:
                print(f"Making continuation request {i+2}...")
                payload = {
                    "context": context,
                    "continuation": next_token
                }
                response = fetcher._client.post(f"https://www.youtube.com/youtubei/v1/next?key={api_key}", json=payload)
                response.raise_for_status()
                continuation_data = response.json()
                save_response(continuation_data, f"continuation_data_{i+2}")

                # Check for replies in this batch
                batch_comments = fetcher._parse_comments(continuation_data)
                replies_in_batch = [c for c in batch_comments if c.get("parent_id")]
                print(f"  Found {len(batch_comments)} comments, {len(replies_in_batch)} replies")

                time.sleep(1)  # Be respectful to the API
            else:
                print(f"No more continuation tokens after request {i+1}")
                break
    else:
        print("No continuation token found")

    print("\nAnalyzing saved data...")

    # Parse comments from initial data
    initial_comments = fetcher._parse_comments(initial_data)
    print(f"Parsed {len(initial_comments)} comments from initial data")

    # Parse comments from continuation data if we have it
    if continuation_token:
        try:
            with open(continuation_file, encoding="utf-8") as f:
                continuation_data = json.load(f)
            continuation_comments = fetcher._parse_comments(continuation_data)
            print(f"Parsed {len(continuation_comments)} comments from continuation data")

            # Show some comment IDs to understand the structure
            for i, comment in enumerate(continuation_comments[:5]):
                print(f"  Comment {i+1}: ID={comment['id']}, Parent={comment['parent_id']}")
                print(f"    Author: {comment['author']}")
                print(f"    Text: {comment['text'][:50]}...")
        except Exception as e:
            print(f"Error parsing continuation data: {e}")

    # Show some comment IDs to understand the structure
    for i, comment in enumerate(initial_comments[:5]):
        print(f"  Comment {i+1}: ID={comment['id']}, Parent={comment['parent_id']}")

    print("\nData files saved for analysis. Check the generated JSON files.")

if __name__ == "__main__":
    main()
