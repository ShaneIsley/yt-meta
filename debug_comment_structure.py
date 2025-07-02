#!/usr/bin/env python3
"""
Debug script to examine the actual structure of comment data from YouTube.
This will help us understand why metadata extraction is returning default values.
"""

import json
import logging
from yt_meta import YtMeta

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

def debug_comment_structure():
    client = YtMeta()
    
    # Get a single comment to examine its structure
    video_url = "https://www.youtube.com/watch?v=B68agR-OeJM"
    
    print("=== Debugging Comment Data Structure ===\n")
    
    # Access the internal comment fetcher to get raw data
    comment_fetcher = client._comment_fetcher
    
    try:
        # Get initial video data
        video_id = "B68agR-OeJM"
        initial_data, ytcfg = comment_fetcher.api_client.get_initial_video_data(video_id)
        
        # Get comment endpoints
        sort_endpoints = comment_fetcher.api_client.get_sort_endpoints_flexible(initial_data, ytcfg)
        print(f"Found endpoints: {list(sort_endpoints.keys())}")
        
        # Get continuation token
        continuation_token = comment_fetcher.api_client.select_sort_endpoint(sort_endpoints, "top")
        print(f"Selected token: {continuation_token[:50]}..." if continuation_token else "No token")
        
        if continuation_token:
            # Make API request
            api_response = comment_fetcher.api_client.make_api_request(continuation_token, ytcfg)
            
            if api_response:
                print("\n=== Analyzing API Response Structure ===")
                
                # Extract different types of payloads
                comment_payloads = comment_fetcher.parser.extract_comment_payloads(api_response)
                author_payloads = comment_fetcher.parser.extract_author_payloads(api_response)
                toolbar_payloads = comment_fetcher.parser.extract_toolbar_payloads(api_response)
                surface_keys = comment_fetcher.parser.get_surface_key_mappings(api_response)
                toolbar_states = comment_fetcher.parser.get_toolbar_states(api_response)
                
                print(f"Comment payloads found: {len(comment_payloads)}")
                print(f"Author payloads found: {len(author_payloads)}")
                print(f"Toolbar payloads found: {len(toolbar_payloads)}")
                print(f"Surface keys found: {len(surface_keys)}")
                print(f"Toolbar states found: {len(toolbar_states)}")
                
                # Examine first comment payload
                if comment_payloads:
                    print("\n=== First Comment Payload Structure ===")
                    first_comment = comment_payloads[0]
                    print(json.dumps(first_comment, indent=2))
                    
                # Examine first author payload
                if author_payloads:
                    print("\n=== First Author Payload Structure ===")
                    first_author_key = list(author_payloads.keys())[0]
                    first_author = author_payloads[first_author_key]
                    print(f"Author key: {first_author_key}")
                    print(json.dumps(first_author, indent=2))
                    
                # Examine first toolbar payload
                if toolbar_payloads:
                    print("\n=== First Toolbar Payload Structure ===")
                    first_toolbar_key = list(toolbar_payloads.keys())[0]
                    first_toolbar = toolbar_payloads[first_toolbar_key]
                    print(f"Toolbar key: {first_toolbar_key}")
                    print(json.dumps(first_toolbar, indent=2))
                    
                # Show surface key mappings
                if surface_keys:
                    print("\n=== Surface Key Mappings ===")
                    for i, (surface_key, comment_id) in enumerate(list(surface_keys.items())[:3]):
                        print(f"{i+1}. {surface_key} -> {comment_id}")
                        
    except Exception as e:
        print(f"Error during debugging: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_comment_structure() 