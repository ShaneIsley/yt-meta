"""
Comment parser for extracting and structuring comment data from YouTube API responses.
"""

import logging
import json
from datetime import date
from typing import Dict, List, Optional, Union, Any

from .date_utils import parse_relative_date_string


logger = logging.getLogger(__name__)


class CommentParser:
    """
    Handles extraction and parsing of comment data from YouTube API responses.
    Responsible for payload extraction, data mapping, and comment structuring.
    """
    
    def extract_comment_payloads(self, api_response: Dict) -> List[Dict]:
        """
        Extract comment payload data from API response.
        
        Args:
            api_response: API response containing comment data
            
        Returns:
            List of comment payload dictionaries
        """
        payloads = []
        
        def search_payloads(obj):
            if isinstance(obj, dict):
                if "commentEntityPayload" in obj:
                    payload = obj["commentEntityPayload"]
                    if "properties" in payload:
                        payloads.append(payload["properties"])
                        
                for value in obj.values():
                    search_payloads(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_payloads(item)
                    
        search_payloads(api_response)
        logger.debug(f"Extracted {len(payloads)} comment payloads")
        return payloads
        
    def extract_author_payloads(self, api_response: Dict) -> Dict[str, Dict]:
        """
        Extract author payload data from API response.
        
        Args:
            api_response: API response containing author data
            
        Returns:
            Dictionary mapping author keys to author data
        """
        authors = {}
        
        def search_authors(obj):
            if isinstance(obj, dict):
                if "authorEntityPayload" in obj:
                    payload = obj["authorEntityPayload"]
                    if "key" in payload:
                        key = payload["key"]
                        authors[key] = payload
                        
                for value in obj.values():
                    search_authors(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_authors(item)
                    
        search_authors(api_response)
        logger.debug(f"Extracted {len(authors)} author payloads")
        return authors
        
    def extract_toolbar_payloads(self, api_response: Dict) -> Dict[str, Dict]:
        """
        Extract toolbar payload data from API response.
        
        Args:
            api_response: API response containing toolbar data
            
        Returns:
            Dictionary mapping toolbar keys to toolbar data
        """
        toolbars = {}
        
        def search_toolbars(obj):
            if isinstance(obj, dict):
                if "engagementToolbarEntityPayload" in obj:
                    payload = obj["engagementToolbarEntityPayload"]
                    if "key" in payload:
                        key = payload["key"]
                        toolbars[key] = payload
                        
                for value in obj.values():
                    search_toolbars(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_toolbars(item)
                    
        search_toolbars(api_response)
        logger.debug(f"Extracted {len(toolbars)} toolbar payloads")
        return toolbars
        
    def get_surface_key_mappings(self, api_response: Dict) -> Dict[str, str]:
        """
        Extract surface key to comment ID mappings from API response.
        
        Args:
            api_response: API response data
            
        Returns:
            Dictionary mapping surface keys to comment IDs
        """
        mappings = {}
        
        def search_mappings(obj):
            if isinstance(obj, dict):
                if "commentSurfaceKey" in obj and "commentId" in obj:
                    surface_key = obj["commentSurfaceKey"]
                    comment_id = obj["commentId"]
                    mappings[surface_key] = comment_id
                    
                for value in obj.values():
                    search_mappings(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_mappings(item)
                    
        search_mappings(api_response)
        logger.debug(f"Extracted {len(mappings)} surface key mappings")
        return mappings
        
    def get_toolbar_states(self, api_response: Dict) -> Dict[str, Dict]:
        """
        Extract toolbar state data from API response.
        
        Args:
            api_response: API response data
            
        Returns:
            Dictionary mapping toolbar keys to state data
        """
        states = {}
        
        def search_states(obj):
            if isinstance(obj, dict):
                if "engagementToolbarStateEntityPayload" in obj:
                    payload = obj["engagementToolbarStateEntityPayload"]
                    if "key" in payload:
                        key = payload["key"]
                        states[key] = payload
                        
                for value in obj.values():
                    search_states(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_states(item)
                    
        search_states(api_response)
        logger.debug(f"Extracted {len(states)} toolbar states")
        return states
        
    def get_paid_comments(self, api_response: Dict, surface_keys: Dict[str, str]) -> Dict[str, str]:
        """
        Extract paid comment (Super Chat) information from API response.
        
        Args:
            api_response: API response data
            surface_keys: Surface key to comment ID mappings
            
        Returns:
            Dictionary mapping comment IDs to paid comment amounts
        """
        paid_comments = {}
        
        def search_paid_comments(obj):
            if isinstance(obj, dict):
                if "commentSurfaceEntityPayload" in obj:
                    payload = obj["commentSurfaceEntityPayload"]
                    if "key" in payload and "pdgCommentChip" in payload:
                        surface_key = payload["key"]
                        if surface_key in surface_keys:
                            comment_id = surface_keys[surface_key]
                            # Extract the paid amount
                            amount = payload.get("simpleText", "Paid Comment")
                            paid_comments[comment_id] = amount
                            
                for value in obj.values():
                    search_paid_comments(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_paid_comments(item)
                    
        search_paid_comments(api_response)
        logger.debug(f"Extracted {len(paid_comments)} paid comments")
        return paid_comments
        
    def extract_reply_continuations(self, api_response: Dict) -> Dict[str, str]:
        """
        Extract reply continuation tokens from comment thread renderers.
        
        Args:
            api_response: API response data containing comment threads
            
        Returns:
            Dictionary mapping comment IDs to their reply continuation tokens
        """
        reply_tokens = {}
        
        def search_comment_threads(obj):
            if isinstance(obj, dict):
                if "commentThreadRenderer" in obj:
                    thread = obj["commentThreadRenderer"]
                    
                    # Get comment ID from commentViewModel
                    comment_id = None
                    if "commentViewModel" in thread:
                        view_model = thread["commentViewModel"]
                        if "commentViewModel" in view_model:
                            comment_id = view_model["commentViewModel"].get("commentId")
                    
                    # Look for reply continuation token
                    if comment_id and "replies" in thread:
                        replies = thread["replies"]
                        if "commentRepliesRenderer" in replies:
                            replies_renderer = replies["commentRepliesRenderer"]
                            if "contents" in replies_renderer:
                                contents = replies_renderer["contents"]
                                for content in contents:
                                    if "continuationItemRenderer" in content:
                                        continuation_item = content["continuationItemRenderer"]
                                        if "continuationEndpoint" in continuation_item:
                                            endpoint = continuation_item["continuationEndpoint"]
                                            if "continuationCommand" in endpoint:
                                                token = endpoint["continuationCommand"].get("token")
                                                if token:
                                                    reply_tokens[comment_id] = token
                                                    logger.debug(f"Found reply token for comment {comment_id}: {token[:50]}...")
                                                    
                for value in obj.values():
                    search_comment_threads(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_comment_threads(item)
                    
        search_comment_threads(api_response)
        logger.debug(f"Extracted {len(reply_tokens)} reply continuation tokens")
        return reply_tokens
        
    def parse_comment_complete(
        self, 
        comment_data: Dict,
        author_payloads: Dict,
        toolbar_payloads: Dict,
        toolbar_states: Dict,
        paid_comments: Dict,
        surface_keys: Dict
    ) -> Optional[Dict[str, Any]]:
        """
        Parse a complete comment with all available metadata.
        
        Args:
            comment_data: Raw comment data from payload
            author_payloads: Author data mappings
            toolbar_payloads: Toolbar data mappings
            toolbar_states: Toolbar state mappings
            paid_comments: Paid comment mappings
            surface_keys: Surface key mappings
            
        Returns:
            Complete comment dictionary or None if parsing fails
        """
        try:
            # Extract basic comment properties
            comment_id = comment_data.get("commentId")
            if not comment_id:
                return None
                
            text = comment_data.get("content", {}).get("content", "")
            
            # Get author information
            author_key = comment_data.get("authorKey", "")
            author_data = author_payloads.get(author_key, {})
            
            author_name = author_data.get("displayName", "Unknown")
            author_channel_id = author_data.get("channelId", "")
            author_avatar_url = ""
            
            # Extract avatar URL from author data
            if "avatarThumbnailUrl" in author_data:
                author_avatar_url = author_data["avatarThumbnailUrl"]
            elif "avatar" in author_data:
                avatar_data = author_data["avatar"]
                if isinstance(avatar_data, dict) and "thumbnails" in avatar_data:
                    thumbnails = avatar_data["thumbnails"]
                    if thumbnails and isinstance(thumbnails, list):
                        # Get the highest resolution thumbnail
                        author_avatar_url = thumbnails[-1].get("url", "")
                        
            # Extract author badges
            author_badges = []
            if "authorBadges" in author_data:
                badges = author_data["authorBadges"]
                for badge in badges:
                    if isinstance(badge, dict):
                        badge_type = badge.get("type", "")
                        if badge_type:
                            author_badges.append(badge_type)
                            
            # Get toolbar/engagement information
            toolbar_key = comment_data.get("toolbarStateKey", "")
            toolbar_data = toolbar_payloads.get(toolbar_key, {})
            toolbar_state = toolbar_states.get(toolbar_key, {})
            
            # Extract engagement counts
            like_count = self._parse_engagement_count(
                toolbar_data.get("likeCountNotliked") or 
                toolbar_data.get("likeCountLiked") or
                toolbar_data.get("likeCount", 0)
            )
            
            reply_count = self._parse_engagement_count(
                toolbar_data.get("replyCount", 0)
            )
            
            # Check if comment is hearted by creator
            heart_state = toolbar_state.get("heartState", "")
            is_hearted = "HEARTED" in heart_state.upper()
            
            # Extract time information
            time_human = comment_data.get("publishedTimeText", "")
            publish_date = None
            time_parsed = None
            
            if time_human:
                try:
                    publish_date = parse_relative_date_string(time_human)
                except Exception:
                    pass
                    
            # Check if this is a reply
            is_reply = bool(comment_data.get("parentCommentKey"))
            parent_id = comment_data.get("parentCommentKey") if is_reply else None
            
            # Check if comment is pinned
            is_pinned = comment_data.get("pinnedText") is not None
            
            # Check for paid comment
            paid_comment = paid_comments.get(comment_id)
            
            return {
                'id': comment_id,
                'text': text,
                'author': author_name,
                'author_channel_id': author_channel_id,
                'author_avatar_url': author_avatar_url,
                'publish_date': publish_date,
                'time_human': time_human,
                'time_parsed': time_parsed,
                'like_count': like_count,
                'reply_count': reply_count,
                'is_hearted': is_hearted,
                'is_reply': is_reply,
                'is_pinned': is_pinned,
                'paid_comment': paid_comment,
                'author_badges': author_badges,
                'parent_id': parent_id,
            }
            
        except Exception as e:
            logger.error(f"Error parsing comment: {e}")
            return None
            
    def _parse_engagement_count(self, count_str: Union[str, int, None]) -> int:
        """
        Parse engagement counts that may be in formats like '1.2K', '58K', '325K'.
        
        Args:
            count_str: Count string or integer
            
        Returns:
            Parsed count as integer
        """
        if isinstance(count_str, int):
            return count_str
            
        if not isinstance(count_str, str):
            return 0
            
        count_str = count_str.strip().upper()
        if not count_str:
            return 0
            
        try:
            # Handle 'K' suffix (thousands)
            if count_str.endswith('K'):
                number_part = count_str[:-1]
                if '.' in number_part:
                    return int(float(number_part) * 1000)
                else:
                    return int(number_part) * 1000
                    
            # Handle 'M' suffix (millions)
            elif count_str.endswith('M'):
                number_part = count_str[:-1]
                if '.' in number_part:
                    return int(float(number_part) * 1000000)
                else:
                    return int(number_part) * 1000000
                    
            # Handle 'B' suffix (billions)
            elif count_str.endswith('B'):
                number_part = count_str[:-1]
                if '.' in number_part:
                    return int(float(number_part) * 1000000000)
                else:
                    return int(number_part) * 1000000000
                    
            # Handle plain numbers
            elif count_str.isdigit():
                return int(count_str)
                
            # Try to parse as float and convert to int
            else:
                return int(float(count_str))
                
        except (ValueError, TypeError):
            logger.warning(f"Could not parse engagement count: {count_str}")
            return 0 