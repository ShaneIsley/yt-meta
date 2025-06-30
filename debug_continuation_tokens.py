#!/usr/bin/env python3
"""
Debug script to trace continuation token behavior and understand
why we're not fetching all 36+ comments.
"""

from yt_meta.comment_fetcher import CommentFetcher


def debug_comment_fetching():
    """Debug the comment fetching process to see where it stops."""
    print("=== DEBUGGING COMMENT FETCHING ===")

    fetcher = CommentFetcher()
    video_url = "https://www.youtube.com/watch?v=feT7_wVmgv0"

    # Get initial page
    response = fetcher._client.get(video_url)
    response.raise_for_status()
    html_content = response.text

    # Extract initial data
    api_key, context = fetcher._find_api_key_and_context(html_content)
    initial_data = fetcher._extract_initial_data(html_content)

    # Get sort endpoints
    sort_endpoints = fetcher._get_sort_endpoints(initial_data)
    print(f"Available sort endpoints: {list(sort_endpoints.keys())}")

    if 'top' not in sort_endpoints:
        print("ERROR: 'top' sort endpoint not found!")
        return

    continuation_endpoint = sort_endpoints['top']
    continuation_token = continuation_endpoint["continuationCommand"]["token"]
    print(f"Initial continuation token: {continuation_token[:50]}...")

    # Track comments and continuation tokens
    all_comments = []
    request_count = 0
    max_requests = 10  # Safety limit

    while continuation_token and request_count < max_requests:
        request_count += 1
        print(f"\n--- Request {request_count} ---")
        print(f"Token: {continuation_token[:50]}...")

        payload = {
            "context": context,
            "continuation": continuation_token
        }

        response = fetcher._client.post(f"https://www.youtube.com/youtubei/v1/next?key={api_key}", json=payload)
        response.raise_for_status()
        continuation_data = response.json()

        # Parse comments from this batch
        batch_comments = fetcher._parse_comments(continuation_data)
        print(f"Comments in this batch: {len(batch_comments)}")

        if batch_comments:
            # Show first comment from batch
            first_comment = batch_comments[0]
            print(f"First comment: {first_comment['author']} - {first_comment['text'][:30]}...")

            # Check if we have replies
            replies = [c for c in batch_comments if c.get('parent_id')]
            if replies:
                print(f"  -> {len(replies)} replies found")

        all_comments.extend(batch_comments)

        # Try to find next continuation token
        next_token = fetcher._find_continuation_token(continuation_data)
        if next_token:
            print(f"Next token found: {next_token[:50]}...")
            continuation_token = next_token
        else:
            print("No more continuation tokens found")

            # Debug: Let's see what's in the response structure
            print("Response keys:", list(continuation_data.keys()))
            if 'onResponseReceivedEndpoints' in continuation_data:
                endpoints = continuation_data['onResponseReceivedEndpoints']
                print(f"Response endpoints: {len(endpoints)}")
                for i, endpoint in enumerate(endpoints):
                    print(f"  Endpoint {i}: {list(endpoint.keys())}")

            # Let's search more broadly for continuation tokens
            def search_continuations(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        new_path = f"{path}.{key}" if path else key
                        if 'continuation' in key.lower():
                            print(f"Found continuation key at {new_path}: {key}")
                        search_continuations(value, new_path)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        search_continuations(item, f"{path}[{i}]")

            print("Searching for any continuation-related keys:")
            search_continuations(continuation_data)
            break

    print("\n=== FINAL RESULTS ===")
    print(f"Total requests made: {request_count}")
    print(f"Total comments fetched: {len(all_comments)}")

    # Breakdown by type
    top_level = [c for c in all_comments if not c.get('parent_id')]
    replies = [c for c in all_comments if c.get('parent_id')]
    print(f"Top-level comments: {len(top_level)}")
    print(f"Replies: {len(replies)}")

    if request_count >= max_requests:
        print(f"WARNING: Stopped at safety limit of {max_requests} requests")

if __name__ == "__main__":
    debug_comment_fetching()
