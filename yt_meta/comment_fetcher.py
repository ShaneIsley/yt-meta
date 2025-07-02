"""
Main comment fetcher that orchestrates API client and parser for comprehensive comment extraction.
"""

import logging
from datetime import date
from typing import Optional, Dict, List, Iterator, Callable, Any

from .exceptions import VideoUnavailableError
from .utils import extract_video_id
from .comment_api_client import CommentAPIClient
from .comment_parser import CommentParser


logger = logging.getLogger(__name__)


class CommentFetcher:
    """
    Main comment fetcher that combines API client and parser for complete comment extraction.
    Provides a clean interface for fetching YouTube comments with comprehensive metadata.
    """
    
    def __init__(self, timeout: int = 30, retries: int = 3, user_agent: Optional[str] = None):
        """Initialize the comment fetcher with HTTP client configuration."""
        self.api_client = CommentAPIClient(timeout, retries, user_agent)
        self.parser = CommentParser()
        
    def __del__(self):
        """Cleanup resources on destruction."""
        if hasattr(self, 'api_client'):
            del self.api_client
            
    def get_comments(
        self, 
        video_id: str, 
        limit: Optional[int] = None,
        sort_by: str = "top",
        since_date: Optional[date] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Get comments from a YouTube video with comprehensive data extraction.
        
        Args:
            video_id: YouTube video ID or URL
            limit: Maximum number of comments to fetch
            sort_by: Sort order ("top" or "recent")
            since_date: Only fetch comments after this date (requires sort_by="recent")
            progress_callback: Callback function called with comment count
            
        Yields:
            Dict containing complete comment data
        """
        # Validate parameters
        if since_date and sort_by != "recent":
            raise ValueError("`since_date` can only be used with `sort_by='recent'`")
            
        video_id = extract_video_id(video_id)
        logger.info(f"Fetching comments for video: {video_id}")
        
        try:
            # Get initial video page data
            initial_data, ytcfg = self.api_client.get_initial_video_data(video_id)
            
            # Get comment sort endpoints with flexible detection
            sort_endpoints = self.api_client.get_sort_endpoints_flexible(initial_data, ytcfg)
            
            if not sort_endpoints:
                logger.warning("No comment sort endpoints found")
                return
                
            # Select appropriate endpoint
            continuation_token = self.api_client.select_sort_endpoint(sort_endpoints, sort_by)
            if not continuation_token:
                logger.warning(f"No continuation token found for sort_by='{sort_by}'")
                return
                
            # Fetch comments using continuation
            comment_count = 0
            seen_ids = set()
            
            while continuation_token and (limit is None or comment_count < limit):
                try:
                    # Make API request for comments
                    api_response = self.api_client.make_api_request(continuation_token, ytcfg)
                    
                    if not api_response:
                        break
                        
                    # Extract all payload data using parser
                    comment_payloads = self.parser.extract_comment_payloads(api_response)
                    author_payloads = self.parser.extract_author_payloads(api_response)
                    toolbar_payloads = self.parser.extract_toolbar_payloads(api_response)
                    
                    # Get mapping data using parser
                    surface_keys = self.parser.get_surface_key_mappings(api_response)
                    toolbar_states = self.parser.get_toolbar_states(api_response)
                    paid_comments = self.parser.get_paid_comments(api_response, surface_keys)
                    
                    # Process comments using parser
                    found_comments = False
                    for comment_data in comment_payloads:
                        if limit and comment_count >= limit:
                            break
                            
                        comment = self.parser.parse_comment_complete(
                            comment_data, 
                            author_payloads, 
                            toolbar_payloads,
                            toolbar_states,
                            paid_comments,
                            surface_keys
                        )
                        
                        if not comment or comment['id'] in seen_ids:
                            continue
                            
                        # Apply date filtering
                        if since_date and comment.get('publish_date'):
                            if comment['publish_date'] < since_date:
                                continue
                                
                        seen_ids.add(comment['id'])
                        comment_count += 1
                        found_comments = True
                        
                        if progress_callback:
                            progress_callback(comment_count)
                            
                        yield comment
                        
                    if not found_comments:
                        break
                        
                    # Get next continuation token using API client
                    continuation_token = self.api_client.extract_continuation_token(api_response)
                    
                except Exception as e:
                    logger.error(f"Error processing comment batch: {e}")
                    break
                    
        except VideoUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Error fetching comments: {e}")
            raise VideoUnavailableError(f"Could not fetch comments for video {video_id}: {e}")


# Maintain backward compatibility with the old class name
BestCommentFetcher = CommentFetcher
