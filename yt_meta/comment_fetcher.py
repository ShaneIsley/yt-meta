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
        progress_callback: Optional[Callable[[int], None]] = None,
        include_reply_continuation: bool = False
    ) -> Iterator[Dict[str, Any]]:
        """
        Get comments from a YouTube video with comprehensive data extraction.
        
        Args:
            video_id: YouTube video ID or URL
            limit: Maximum number of comments to fetch
            sort_by: Sort order ("top" or "recent")
            since_date: Only fetch comments after this date (requires sort_by="recent")
            progress_callback: Callback function called with comment count
            include_reply_continuation: Include reply continuation tokens for comments with replies
            
        Yields:
            Dict containing complete comment data, optionally including 'reply_continuation_token'
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
                    
                    # Extract reply continuation tokens if requested
                    reply_tokens = {}
                    if include_reply_continuation:
                        reply_tokens = self.parser.extract_reply_continuations(api_response)
                    
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
                        
                        # Add reply continuation token if available and requested
                        if include_reply_continuation and comment['id'] in reply_tokens:
                            comment['reply_continuation_token'] = reply_tokens[comment['id']]
                        
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

    def get_comment_replies(
        self,
        video_id: str,
        reply_continuation_token: str,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Get replies for a specific comment using its reply continuation token.
        
        Args:
            video_id: YouTube video ID or URL
            reply_continuation_token: Reply continuation token from a comment
            limit: Maximum number of replies to fetch
            progress_callback: Callback function called with reply count
            
        Yields:
            Dict containing complete reply data
        """
        video_id = extract_video_id(video_id)
        logger.info(f"Fetching replies for video: {video_id}")
        
        try:
            # Get initial video page data for ytcfg
            _, ytcfg = self.api_client.get_initial_video_data(video_id)
            
            # Fetch replies using continuation
            reply_count = 0
            seen_ids = set()
            continuation_token = reply_continuation_token
            
            while continuation_token and (limit is None or reply_count < limit):
                try:
                    # Make API request for replies
                    api_response = self.api_client.make_reply_request(continuation_token, ytcfg)
                    
                    if not api_response:
                        break
                        
                    # Extract replies from the response
                    # Replies come in onResponseReceivedEndpoints.appendContinuationItemsAction.continuationItems
                    replies_found = False
                    
                    if "onResponseReceivedEndpoints" in api_response:
                        for endpoint in api_response["onResponseReceivedEndpoints"]:
                            if "appendContinuationItemsAction" in endpoint:
                                action = endpoint["appendContinuationItemsAction"]
                                if "continuationItems" in action:
                                    for item in action["continuationItems"]:
                                        if "commentRenderer" in item:
                                            reply_data = item["commentRenderer"]
                                            
                                            # Parse reply as a comment but mark it as a reply
                                            reply = self._parse_reply_comment(reply_data)
                                            
                                            if not reply or reply['id'] in seen_ids:
                                                continue
                                                
                                            if limit and reply_count >= limit:
                                                break
                                                
                                            seen_ids.add(reply['id'])
                                            reply_count += 1
                                            replies_found = True
                                            
                                            if progress_callback:
                                                progress_callback(reply_count)
                                                
                                            yield reply
                                            
                    if not replies_found:
                        break
                        
                    # Look for next continuation token for more replies
                    continuation_token = self.api_client.extract_continuation_token(api_response)
                    
                except Exception as e:
                    logger.error(f"Error processing reply batch: {e}")
                    break
                    
        except VideoUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Error fetching replies: {e}")
            raise VideoUnavailableError(f"Could not fetch replies for video {video_id}: {e}")
            
    def _parse_reply_comment(self, reply_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Parse a reply comment from commentRenderer data.
        
        Args:
            reply_data: Raw reply data from commentRenderer
            
        Returns:
            Parsed reply comment or None if parsing fails
        """
        try:
            comment_id = reply_data.get("commentId", "")
            if not comment_id:
                return None
                
            # Extract text content
            text = ""
            if "contentText" in reply_data:
                content = reply_data["contentText"]
                if "runs" in content:
                    text = "".join(run.get("text", "") for run in content["runs"])
                elif "simpleText" in content:
                    text = content["simpleText"]
                    
            # Extract author information
            author = "Unknown"
            if "authorText" in reply_data:
                author_text = reply_data["authorText"]
                if "simpleText" in author_text:
                    author = author_text["simpleText"]
                    
            # Extract author channel ID
            author_channel_id = ""
            if "authorEndpoint" in reply_data:
                endpoint = reply_data["authorEndpoint"]
                if "browseEndpoint" in endpoint:
                    browse_endpoint = endpoint["browseEndpoint"]
                    author_channel_id = browse_endpoint.get("browseId", "")
                    
            # Extract author avatar
            author_avatar_url = ""
            if "authorThumbnail" in reply_data:
                thumbnail = reply_data["authorThumbnail"]
                if "thumbnails" in thumbnail and thumbnail["thumbnails"]:
                    # Get the highest resolution thumbnail
                    author_avatar_url = thumbnail["thumbnails"][-1].get("url", "")
                    
            # Extract engagement counts
            like_count = reply_data.get("likeCount", 0)
            if isinstance(like_count, str):
                like_count = self.parser._parse_engagement_count(like_count)
                
            # Extract time information
            time_human = ""
            if "publishedTimeText" in reply_data:
                time_text = reply_data["publishedTimeText"]
                if "runs" in time_text:
                    time_human = "".join(run.get("text", "") for run in time_text["runs"])
                elif "simpleText" in time_text:
                    time_human = time_text["simpleText"]
                    
            # Parse time to date
            publish_date = None
            if time_human:
                try:
                    from .date_utils import parse_relative_date_string
                    publish_date = parse_relative_date_string(time_human)
                except Exception:
                    pass
                    
            # Extract reply-specific information
            is_reply = reply_data.get("isReply", True)  # Default to True for replies
            parent_id = reply_data.get("parentId", "")
            
            # Check if author is channel owner
            is_hearted = reply_data.get("authorIsChannelOwner", False)
            
            return {
                'id': comment_id,
                'text': text,
                'author': author,
                'author_channel_id': author_channel_id,
                'author_avatar_url': author_avatar_url,
                'publish_date': publish_date,
                'time_human': time_human,
                'time_parsed': None,
                'like_count': like_count,
                'reply_count': 0,  # Replies don't have nested replies in YouTube
                'is_hearted': is_hearted,
                'is_reply': is_reply,
                'is_pinned': False,  # Replies can't be pinned
                'paid_comment': None,
                'author_badges': [],
                'parent_id': parent_id,
            }
            
        except Exception as e:
            logger.error(f"Error parsing reply comment: {e}")
            return None


# Maintain backward compatibility with the old class name
BestCommentFetcher = CommentFetcher
