#!/usr/bin/env python3
"""
Debug script to find all payload types in the API response.
"""

import json
from yt_meta import YtMeta

def find_all_payloads():
    client = YtMeta()
    comment_fetcher = client._comment_fetcher
    
    try:
        # Get API response
        video_id = "B68agR-OeJM"
        initial_data, ytcfg = comment_fetcher.api_client.get_initial_video_data(video_id)
        sort_endpoints = comment_fetcher.api_client.get_sort_endpoints_flexible(initial_data, ytcfg)
        continuation_token = comment_fetcher.api_client.select_sort_endpoint(sort_endpoints, "top")
        api_response = comment_fetcher.api_client.make_api_request(continuation_token, ytcfg)
        
        if api_response:
            print("=== Searching for all payload types ===\n")
            
            # Search for all payload types
            payload_types = set()
            
            def find_payloads(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if key.endswith("Payload"):
                            payload_types.add(key)
                            if len(path.split('.')) < 6:  # Avoid too deep paths
                                print(f"Found {key} at: {path}.{key}")
                        find_payloads(value, f"{path}.{key}" if path else key)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        find_payloads(item, f"{path}[{i}]" if path else f"[{i}]")
            
            find_payloads(api_response)
            
            print(f"\n=== Summary ===")
            print(f"Total unique payload types found: {len(payload_types)}")
            for payload_type in sorted(payload_types):
                print(f"  - {payload_type}")
                
            # Look specifically for author-related data
            print(f"\n=== Looking for author-related keys ===")
            author_keys = set()
            
            def find_author_keys(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if "author" in key.lower():
                            author_keys.add(key)
                            if len(path.split('.')) < 6:
                                print(f"Found author key '{key}' at: {path}.{key}")
                        find_author_keys(value, f"{path}.{key}" if path else key)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        find_author_keys(item, f"{path}[{i}]" if path else f"[{i}]")
            
            find_author_keys(api_response)
            
            print(f"\nTotal author-related keys: {len(author_keys)}")
            for key in sorted(author_keys):
                print(f"  - {key}")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    find_all_payloads() 