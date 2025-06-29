import json
import re
import httpx

YT_CFG_RE = r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;'
YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'
YOUTUBE_VIDEO_URL = 'https://www.youtube.com/watch?v={youtube_id}'
YOUTUBE_API_URL = "https://www.youtube.com/youtubei/v1/next"
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'


class CommentFetcher:

    def __init__(self):
        self._client = httpx.Client(headers={'User-Agent': USER_AGENT})

    def get_comments(self, youtube_id: str, sort_by: str = "top"):
        """
        Fetch comments for a YouTube video.
        
        Args:
            youtube_id: The YouTube video ID
            sort_by: Comment sorting method ('top' or 'recent')
        """
        # 1. Get initial page
        response = self._client.get(YOUTUBE_VIDEO_URL.format(youtube_id=youtube_id))
        response.raise_for_status()
        html_content = response.text

        # 2. Extract initial data
        api_key, context = self._find_api_key_and_context(html_content)
        initial_data = self._extract_initial_data(html_content)
        
        # 3. Get the correct continuation token based on sort preference
        sort_endpoints = self._get_sort_endpoints(initial_data)
        if sort_by not in sort_endpoints:
            raise ValueError(f"Invalid sort_by value: '{sort_by}'. Available options are: {list(sort_endpoints.keys())}")
        
        continuation_endpoint = sort_endpoints[sort_by]
        
        # 4. Process all continuations (including replies) using a queue
        continuations = [continuation_endpoint]
        
        while continuations:
            continuation = continuations.pop(0)  # Process in order
            
            payload = {
                "context": context,
                "continuation": continuation["continuationCommand"]["token"]
            }
            
            response = self._client.post(f"{YOUTUBE_API_URL}?key={api_key}", json=payload)
            response.raise_for_status()
            continuation_data = response.json()

            # Parse and yield comments from this response
            comments = self._parse_comments(continuation_data)
            yield from comments

            # Find all continuation endpoints in this response
            new_continuations = self._find_all_continuation_endpoints(continuation_data)
            continuations.extend(new_continuations)

    def _find_all_continuation_endpoints(self, data: dict) -> list[dict]:
        """
        Find all continuation endpoints in a response, including reply continuations.
        Based on the original youtube-comment-downloader approach.
        """
        continuations = []
        
        # Look for reloadContinuationItemsCommand and appendContinuationItemsAction
        actions = list(self._search_dict(data, 'reloadContinuationItemsCommand')) + \
                  list(self._search_dict(data, 'appendContinuationItemsAction'))
        
        for action in actions:
            for item in action.get('continuationItems', []):
                target_id = action.get('targetId', '')
                
                # Process continuations for comments and replies
                if target_id in ['comments-section', 
                               'engagement-panel-comments-section',
                               'shorts-engagement-panel-comments-section']:
                    # Find continuation endpoints in this item
                    endpoints = list(self._search_dict(item, 'continuationEndpoint'))
                    for endpoint in endpoints:
                        if 'continuationCommand' in endpoint:
                            continuations.append(endpoint)
                
                # Process 'Show more replies' buttons
                if target_id.startswith('comment-replies-item') and 'continuationItemRenderer' in item:
                    button_renderer = next(self._search_dict(item, 'buttonRenderer'), None)
                    if button_renderer and 'command' in button_renderer:
                        command = button_renderer['command']
                        if 'continuationCommand' in command:
                            continuations.append(command)
        
        return continuations

    def _regex_search(self, text, pattern, group=1, default=None):
        match = re.search(pattern, text)
        return match.group(group) if match else default

    def _search_dict(self, partial, search_key):
        stack = [partial]
        while stack:
            current_item = stack.pop()
            if isinstance(current_item, dict):
                for key, value in current_item.items():
                    if key == search_key:
                        yield value
                    else:
                        stack.append(value)
            elif isinstance(current_item, list):
                for item in current_item:
                    stack.append(item)
    
    def _extract_initial_data(self, html_content: str) -> dict:
        return json.loads(self._regex_search(html_content, YT_INITIAL_DATA_RE, default='{}'))

    def _find_continuation_token(self, data: dict) -> str | None:
        # First try the engagement panels (where comments are located on initial page load)
        engagement_panels = data.get('engagementPanels', [])
        for panel in engagement_panels:
            if 'engagementPanelSectionListRenderer' in panel:
                # Check if this is the comments panel
                header = panel['engagementPanelSectionListRenderer'].get('header', {})
                title_header = header.get('engagementPanelTitleHeaderRenderer', {})
                title = title_header.get('title', {}).get('runs', [{}])[0].get('text', '')
                
                if 'comments' in title.lower():
                    # Look for continuation in the content
                    content = panel['engagementPanelSectionListRenderer'].get('content', {})
                    continuations = self._search_dict(content, 'continuationEndpoint')
                    for continuation in continuations:
                        if continuation:
                            token = continuation.get("continuationCommand", {}).get("token")
                            if token:
                                return token
        
        # Check onResponseReceivedEndpoints for continuation items
        endpoints = data.get('onResponseReceivedEndpoints', [])
        for endpoint in endpoints:
            # Check appendContinuationItemsAction
            if 'appendContinuationItemsAction' in endpoint:
                action = endpoint['appendContinuationItemsAction']
                items = action.get('continuationItems', [])
                for item in items:
                    if 'continuationItemRenderer' in item:
                        renderer = item['continuationItemRenderer']
                        if 'continuationEndpoint' in renderer:
                            cont_endpoint = renderer['continuationEndpoint']
                            token = cont_endpoint.get('continuationCommand', {}).get('token')
                            if token:
                                return token
            
            # Check reloadContinuationItemsCommand
            if 'reloadContinuationItemsCommand' in endpoint:
                command = endpoint['reloadContinuationItemsCommand']
                items = command.get('continuationItems', [])
                for item in items:
                    if 'continuationItemRenderer' in item:
                        renderer = item['continuationItemRenderer']
                        if 'continuationEndpoint' in renderer:
                            cont_endpoint = renderer['continuationEndpoint']
                            token = cont_endpoint.get('continuationCommand', {}).get('token')
                            if token:
                                return token
        
        # Fallback to the original search method for any other continuation structures
        continuations = self._search_dict(data, 'continuationEndpoint')
        for continuation in continuations:
            if continuation:
                 token = continuation.get("continuationCommand", {}).get("token")
                 if token:
                     return token
        return None

    def _parse_comments(self, data: dict) -> list[dict]:
        comments = []
        
        # Handle continuation responses - comments are in frameworkUpdates
        framework = data.get('frameworkUpdates', {})
        entity_batch = framework.get('entityBatchUpdate', {})
        mutations = entity_batch.get('mutations', [])
        
        for mutation in mutations:
            if 'payload' in mutation and 'commentEntityPayload' in mutation['payload']:
                payload = mutation['payload']['commentEntityPayload']
                comments.append(self._parse_comment_payload(payload))
        
        # If we found comments in frameworkUpdates, return them
        if comments:
            return comments
        
        # Fallback: search for commentEntityPayload anywhere in the data (for other structures)
        comment_payloads = self._search_dict(data, 'commentEntityPayload')
        for payload in comment_payloads:
            comments.append(self._parse_comment_payload(payload))
            
        return comments
    
    def _parse_comment_payload(self, payload: dict) -> dict:
        """Parse a single commentEntityPayload into our comment format."""
        properties = payload.get("properties", {})
        author = payload.get("author", {})
        toolbar = payload.get("toolbar", {})

        text = properties.get("content", {}).get("content", "")
        
        # Extract comment ID and determine parent relationship
        comment_id = properties.get("commentId")
        parent_id = None
        if comment_id and '.' in comment_id:
            parent_id = comment_id.split('.')[0]
        
        likes_str = toolbar.get("likeCountNotliked", "0").strip()
        likes = 0
        try:
            likes = int(likes_str)
        except (ValueError, TypeError):
            pass
        
        reply_count_str = toolbar.get("replyCount", "0")
        if isinstance(reply_count_str, int):
            replies = reply_count_str
        else:
            try:
                replies = int(str(reply_count_str).strip())
            except (ValueError, TypeError):
                replies = 0
        
        # Detect pinned comments
        is_pinned = False
        # Check for explicit isPinned flag
        if properties.get("isPinned"):
            is_pinned = True
        # Check if author is creator (common indicator of pinned comments)
        elif author.get("isCreator"):
            is_pinned = True
        
        return {
            "id": comment_id,
            "parent_id": parent_id,
            "text": text,
            "author": author.get("displayName"),
            "author_channel_id": author.get("channelId"),
            "author_avatar_url": author.get("avatarThumbnailUrl"),
            "likes": likes,
            "reply_count": replies,
            "published_time": properties.get("publishedTime"),
            "is_pinned": is_pinned,
        }

    def _find_api_key_and_context(self, html_content: str) -> tuple[str, dict]:
        ytcfg = json.loads(self._regex_search(html_content, YT_CFG_RE, default='{}'))
        if not ytcfg:
            raise ValueError("Could not find ytcfg in HTML")
        
        api_key = ytcfg.get("INNERTUBE_API_KEY")
        context = ytcfg.get("INNERTUBE_CONTEXT")

        if not api_key or not context:
            raise ValueError("Could not find API key or context in ytcfg")

        return api_key, context 

    def _get_sort_endpoints(self, data: dict) -> dict:
        """Finds the continuation endpoints for comment sorting."""
        endpoints = {}
        
        # Look for sort menu in engagement panels
        engagement_panels = data.get('engagementPanels', [])
        for panel in engagement_panels:
            if 'engagementPanelSectionListRenderer' in panel:
                header = panel['engagementPanelSectionListRenderer'].get('header', {})
                title_header = header.get('engagementPanelTitleHeaderRenderer', {})
                title = title_header.get('title', {}).get('runs', [{}])[0].get('text', '')
                
                if 'comments' in title.lower() and 'menu' in title_header:
                    sort_menu = title_header['menu'].get('sortFilterSubMenuRenderer')
                    if sort_menu:
                        for item in sort_menu.get('subMenuItems', []):
                            title = item.get('title', '').lower()
                            token = item.get('serviceEndpoint', {}).get('continuationCommand', {}).get('token')
                            if not token:
                                continue

                            if 'newest' in title:
                                endpoints['recent'] = item['serviceEndpoint']
                            elif 'top' in title:
                                endpoints['top'] = item['serviceEndpoint']
                        return endpoints
        
        # Fallback to generic search
        sort_menu = next(self._search_dict(data, 'sortFilterSubMenuRenderer'), None)
        if not sort_menu:
            # If we can't find the sort menu, we can't offer sorting.
            # We can still find the default continuation token for the page.
            token = self._find_continuation_token(data)
            if token:
                 # The structure of an endpoint is a dict containing the command and token.
                 # We create a synthetic one here to match the expected structure.
                endpoints['top'] = {'continuationCommand': {'token': token}}
            return endpoints

        for item in sort_menu.get('subMenuItems', []):
            title = item.get('title', '').lower()
            token = item.get('serviceEndpoint', {}).get('continuationCommand', {}).get('token')
            if not token:
                continue

            if 'newest' in title:
                endpoints['recent'] = item['serviceEndpoint']
            elif 'top' in title:
                endpoints['top'] = item['serviceEndpoint']
        return endpoints 