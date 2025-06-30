import json
import os
import sys

from yt_meta.comment_fetcher import CommentFetcher

# Ensure the package is in the path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

def main():
    """
    Fetches the first continuation response for a video and prints it.
    This is a debugging script to inspect the live API structure.
    """
    video_url = "https://www.youtube.com/watch?v=feT7_wVmgv0"

    # We need to access the raw response, so we'll temporarily modify the fetcher
    original_fetch_continuation = CommentFetcher._fetch_continuation

    continuation_data_holder = {}

    def new_fetch_continuation(self, token, key, context):
        print("\n--- Intercepting _fetch_continuation call ---")
        data = original_fetch_continuation(self, token, key, context)
        continuation_data_holder['data'] = data
        # To stop the generator, we return a response with no new token
        return {"frameworkUpdates": {}}

    CommentFetcher._fetch_continuation = new_fetch_continuation

    fetcher = CommentFetcher()

    print("--- Calling get_comments to trigger the fetch ---")
    # Fetch just enough to trigger one continuation call
    comments_generator = fetcher.get_comments(video_url, limit=25)
    try:
        for _ in comments_generator:
            pass
    except Exception as e:
        print(f"Generator stopped as expected. Error: {e}")

    print("\n--- Raw Continuation JSON Response ---")
    if 'data' in continuation_data_holder:
        print(json.dumps(continuation_data_holder['data'], indent=2))
    else:
        print("Failed to capture continuation data.")

    # Restore original method
    CommentFetcher._fetch_continuation = original_fetch_continuation


if __name__ == "__main__":
    main()
