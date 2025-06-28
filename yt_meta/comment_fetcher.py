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
        continuation_token = continuation_endpoint["continuationCommand"]["token"]

        # 4. Yield initial comments
        comments = self._parse_comments(initial_data)
        yield from comments

        # 5. Process continuations
        while continuation_token:
            payload = {
                "context": context,
                "continuation": continuation_token
            }
            response = self._client.post(f"{YOUTUBE_API_URL}?key={api_key}", json=payload)
            response.raise_for_status()
            continuation_data = response.json()

            comments = self._parse_comments(continuation_data)
            yield from comments

            continuation_token = self._find_continuation_token(continuation_data)

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
        continuations = self._search_dict(data, 'continuationEndpoint')
        for continuation in continuations:
            if continuation:
                 return continuation.get("continuationCommand", {}).get("token")
        return None

    def _parse_comments(self, data: dict) -> list[dict]:
        comments = []
        comment_payloads = self._search_dict(data, 'commentEntityPayload')

        for payload in comment_payloads:
            properties = payload.get("properties", {})
            author = payload.get("author", {})
            toolbar = payload.get("toolbar", {})

            text = properties.get("content", {}).get("content", "")
            
            likes_str = toolbar.get("likeCountNotliked", "0").strip()
            if not likes_str or not likes_str.isdigit():
                likes_str = "0"
            likes = int(likes_str)

            reply_count_str = toolbar.get("replyCount", "0").strip()
            if not reply_count_str or not reply_count_str.isdigit():
                reply_count_str = "0"
            replies = int(reply_count_str)
            
            comments.append({
                "id": properties.get("commentId"),
                "text": text,
                "author": author.get("displayName"),
                "author_channel_id": author.get("channelId"),
                "author_avatar_url": author.get("avatarThumbnailUrl"),
                "likes": likes,
                "reply_count": replies,
                "published_time": properties.get("publishedTime"),
            })
        return comments

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