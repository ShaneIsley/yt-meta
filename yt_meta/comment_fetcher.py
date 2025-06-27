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

    def get_comments(self, youtube_id: str):
        # 1. Get initial page
        response = self._client.get(YOUTUBE_VIDEO_URL.format(youtube_id=youtube_id))
        response.raise_for_status()
        html_content = response.text

        # 2. Extract initial data
        api_key, context = self._find_api_key_and_context(html_content)
        initial_data = self._extract_initial_data(html_content)
        
        # 3. Yield initial comments
        comments = self._parse_comments(initial_data)
        yield from comments

        # 4. Process continuations
        continuation_token = self._find_continuation_token(initial_data)
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
        comment_renderers = self._search_dict(data, 'commentRenderer')

        for renderer in comment_renderers:
            text_runs = renderer.get("contentText", {}).get("runs", [])
            text = "".join(run.get("text", "") for run in text_runs)
            
            likes_str = renderer.get("voteCount", {}).get("simpleText", "0")
            if "K" in likes_str or "M" in likes_str:
                likes_str = likes_str.strip().upper()
                if likes_str.endswith("K"):
                    likes = int(float(likes_str[:-1]) * 1000)
                elif likes_str.endswith("M"):
                    likes = int(float(likes_str[:-1]) * 1000000)
                else:
                    likes = 0
            elif likes_str.isdigit():
                likes = int(likes_str)
            else: # Can be 'Like' or some other string
                likes = 0
            
            comments.append({
                "id": renderer.get("commentId"),
                "text": text,
                "author": renderer.get("authorText", {}).get("simpleText"),
                "likes": likes,
                "published_time": renderer.get("publishedTimeText", {}).get("runs", [{}])[0].get("text"),
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