"""
Comment API client for handling HTTP operations and YouTube API interaction.
"""

import json
import re
import logging
from typing import Optional, Dict
import httpx

from .exceptions import VideoUnavailableError


logger = logging.getLogger(__name__)


class CommentAPIClient:
    """
    Handles HTTP operations and YouTube API interaction for comment fetching.
    Responsible for endpoint detection, API requests, and data retrieval.
    """
    
    def __init__(self, timeout: int = 30, retries: int = 3, user_agent: Optional[str] = None):
        """Initialize the API client with HTTP client configuration."""
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True
        )
        
    def __del__(self):
        """Cleanup HTTP client on destruction."""
        if hasattr(self, 'client'):
            self.client.close()
            
    def get_initial_video_data(self, video_id: str) -> tuple[Dict, Dict]:
        """Get initial video page data and ytcfg."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        try:
            response = self.client.get(url)
            response.raise_for_status()
            html_content = response.text
            
            ytcfg = self._extract_ytcfg(html_content)
            initial_data = self._extract_initial_data(html_content)
            
            return initial_data, ytcfg
            
        except Exception as e:
            raise VideoUnavailableError(f"Could not load video page: {e}")
            
    def _extract_ytcfg(self, html_content: str) -> Dict:
        """Extract ytcfg configuration from HTML."""
        ytcfg_pattern = r'ytcfg\.set\s*\(\s*({.+?})\s*\)'
        match = re.search(ytcfg_pattern, html_content, re.DOTALL)
        
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
                
        return {}
        
    def _extract_initial_data(self, html_content: str) -> Dict:
        """Extract ytInitialData from HTML."""
        initial_data_pattern = r'var\s+ytInitialData\s*=\s*({.+?});'
        match = re.search(initial_data_pattern, html_content, re.DOTALL)
        
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
                
        return {}
        
    def get_sort_endpoints_flexible(self, initial_data: Dict, ytcfg: Dict) -> Dict[str, str]:
        """
        Flexibly detect comment sort endpoints from various locations in the YouTube response.
        This method searches multiple places for comment sorting options to be resilient
        to YouTube's changing structure.
        """
        endpoints = {}
        
        def find_sort_filter_menus(obj, path=""):
            """Recursively search for sortFilterSubMenuRenderer anywhere in the data."""
            if isinstance(obj, dict):
                if "sortFilterSubMenuRenderer" in obj:
                    submenu = obj["sortFilterSubMenuRenderer"]
                    if "subMenuItems" in submenu:
                        logger.debug(f"Found sortFilterSubMenuRenderer at path: {path}")
                        for item in submenu["subMenuItems"]:
                            title = item.get("title", "").lower()
                            endpoint = item.get("serviceEndpoint", {}).get("continuationCommand", {}).get("token")
                            if endpoint:
                                endpoints[title] = endpoint
                                logger.debug(f"Added endpoint: {title} -> {endpoint[:50]}...")
                                
                for key, value in obj.items():
                    find_sort_filter_menus(value, f"{path}.{key}" if path else key)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_sort_filter_menus(item, f"{path}[{i}]" if path else f"[{i}]")
        
        def find_engagement_panels(obj):
            """Look for engagement panels that might contain comment endpoints."""
            if isinstance(obj, dict):
                if "engagementPanels" in obj:
                    panels = obj["engagementPanels"]
                    for panel in panels:
                        if self._is_comment_panel(panel):
                            self._extract_endpoints_from_panel(panel, endpoints)
                            
                for value in obj.values():
                    find_engagement_panels(value)
            elif isinstance(obj, list):
                for item in obj:
                    find_engagement_panels(item)
        
        def find_continuation_tokens(obj):
            """Look for continuation tokens that might be comment-related."""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if "token" in key.lower() and isinstance(value, str):
                        if self._is_comment_token(value):
                            # Try to determine if this is top or recent based on context
                            context_key = key.lower()
                            if "top" in context_key or "best" in context_key:
                                endpoints["top comments"] = value
                            elif "new" in context_key or "recent" in context_key:
                                endpoints["newest first"] = value
                            else:
                                endpoints[f"comments_{len(endpoints)}"] = value
                                
                for value in obj.values():
                    find_continuation_tokens(value)
            elif isinstance(obj, list):
                for item in obj:
                    find_continuation_tokens(item)
        
        # Search strategies in order of preference
        find_sort_filter_menus(initial_data)
        
        if not endpoints:
            find_engagement_panels(initial_data)
            
        if not endpoints:
            find_continuation_tokens(initial_data)
            
        logger.info(f"Found {len(endpoints)} comment endpoints: {list(endpoints.keys())}")
        return endpoints
        
    def _is_comment_panel(self, panel: Dict) -> bool:
        """Determine if an engagement panel is related to comments."""
        panel_str = json.dumps(panel).lower()
        return any(keyword in panel_str for keyword in ["comment", "discussion", "engagement"])
        
    def _extract_endpoints_from_panel(self, panel: Dict, endpoints: Dict):
        """Extract continuation tokens from an engagement panel."""
        def extract_tokens(obj):
            if isinstance(obj, dict):
                # Look for continuation commands
                if "continuationCommand" in obj:
                    token = obj["continuationCommand"].get("token")
                    if token and self._is_comment_token(token):
                        # Try to determine sort type from context
                        context = json.dumps(obj).lower()
                        if "top" in context or "best" in context:
                            endpoints["top comments"] = token
                        elif "new" in context or "recent" in context:
                            endpoints["newest first"] = token
                        else:
                            endpoints[f"comments_{len(endpoints)}"] = token
                            
                for value in obj.values():
                    extract_tokens(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_tokens(item)
        
        extract_tokens(panel)
        
    def _is_comment_token(self, token: str) -> bool:
        """
        Determine if a continuation token is likely for comments.
        Comment tokens typically have certain patterns.
        """
        if not isinstance(token, str) or len(token) < 10:
            return False
            
        # Comment tokens often contain these patterns
        comment_indicators = ["comments", "discussion", "4qmFsgI", "replies"]
        token_lower = token.lower()
        
        return any(indicator in token_lower for indicator in comment_indicators)
        
    def select_sort_endpoint(self, endpoints: Dict[str, str], sort_by: str) -> Optional[str]:
        """
        Select the appropriate endpoint based on the requested sort order.
        
        Args:
            endpoints: Dictionary of available endpoints
            sort_by: Requested sort order ("top" or "recent")
            
        Returns:
            Continuation token for the requested sort order
        """
        if not endpoints:
            return None
            
        # Mapping of sort preferences to endpoint keywords
        if sort_by == "top":
            preferences = ["top comments", "top", "best comments", "best"]
        elif sort_by == "recent":
            preferences = ["newest first", "newest", "recent", "new comments", "latest"]
        else:
            preferences = ["top comments", "top", "best comments"]
            
        # Try to find exact matches first
        for pref in preferences:
            for endpoint_name, token in endpoints.items():
                if pref.lower() in endpoint_name.lower():
                    logger.info(f"Selected endpoint: {endpoint_name} for sort_by='{sort_by}'")
                    return token
                    
        # Fallback to first available endpoint
        if endpoints:
            first_endpoint = list(endpoints.keys())[0]
            token = endpoints[first_endpoint]
            logger.info(f"Fallback to endpoint: {first_endpoint} for sort_by='{sort_by}'")
            return token
            
        return None
        
    def make_api_request(self, continuation_token: str, ytcfg: Dict) -> Optional[Dict]:
        """
        Make API request to get comment data using continuation token.
        
        Args:
            continuation_token: Token for the API request
            ytcfg: YouTube configuration data
            
        Returns:
            API response data or None if failed
        """
        api_key = ytcfg.get("INNERTUBE_API_KEY")
        if not api_key:
            logger.error("No API key found in ytcfg")
            return None
            
        url = f"https://www.youtube.com/youtubei/v1/next?key={api_key}"
        
        context = ytcfg.get("INNERTUBE_CONTEXT", {})
        
        payload = {
            "context": context,
            "continuation": continuation_token
        }
        
        try:
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None
            
    def extract_continuation_token(self, api_response: Dict) -> Optional[str]:
        """
        Extract the next continuation token from API response.
        
        Args:
            api_response: API response data
            
        Returns:
            Next continuation token or None if not found
        """
        def search_for_continuation(obj):
            if isinstance(obj, dict):
                # Look for continuation commands
                if "continuationCommand" in obj:
                    token = obj["continuationCommand"].get("token")
                    if token and self._is_comment_token(token):
                        return token
                        
                # Look for next continuation endpoints
                if "nextContinuationData" in obj:
                    token = obj["nextContinuationData"].get("continuation")
                    if token:
                        return token
                        
                # Recursively search all values
                for value in obj.values():
                    result = search_for_continuation(value)
                    if result:
                        return result
                        
            elif isinstance(obj, list):
                for item in obj:
                    result = search_for_continuation(item)
                    if result:
                        return result
                        
            return None
            
        return search_for_continuation(api_response) 