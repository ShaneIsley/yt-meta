import json
import re
from collections.abc import Callable, Iterator
from datetime import date

import httpx
import base64
import urllib.parse

from yt_meta import date_utils
from yt_meta.exceptions import VideoUnavailableError

from . import constants as const

YT_CFG_RE = r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;'
YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'
YOUTUBE_VIDEO_URL = 'https://www.youtube.com/watch?v={youtube_id}'
YOUTUBE_API_URL = "https://www.youtube.com/youtubei/v1/next"
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'


class CommentFetcher:

    def __init__(self):
        self._client = httpx.Client(headers={'User-Agent': const.USER_AGENT})

    def get_comments(
        self,
        video_id: str,
        sort_by: str = "top",
        limit: int | None = None,
        include_reply_continuation: bool = False,
        since_date: date | None = None,
        progress_callback: Callable[[int], None] | None = None,
    ) -> Iterator[dict]:
        if since_date and sort_by != "recent":
            raise ValueError("`since_date` can only be used with `sort_by='recent'`")

        initial_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            response = self._client.get(initial_url, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise VideoUnavailableError(f"Failed to fetch video page: {e}") from e
        html = response.text

        initial_data = self._extract_initial_data(html)
        if not initial_data:
            return

        api_key, context = self._find_api_key_and_context(html)
        continuation_token, a, b = self._get_sort_endpoints(initial_data).get(sort_by, (None, None, None))

        # Fix endpoint mapping - try exact match first, then partial match
        if sort_by not in self._get_sort_endpoints(initial_data):
            for endpoint_key in self._get_sort_endpoints(initial_data):
                if sort_by in endpoint_key or endpoint_key in sort_by:
                    continuation_token, a, b = self._get_sort_endpoints(initial_data)[endpoint_key]
                    break

        comments = self._parse_comments(initial_data)
        count = 0
        for comment in comments:
            if limit is not None and count >= limit:
                return

            if since_date and comment.get("publish_date") and comment.get("publish_date") < since_date:
                continuation_token = None
                break

            yield comment
            count += 1
            if progress_callback:
                progress_callback(count)

        while continuation_token and (limit is None or count < limit):
            continuation_url = f"https://www.youtube.com/youtubei/v1/next?key={api_key}"
            payload = {"context": context, "continuation": continuation_token}
            try:
                response = self._client.post(continuation_url, json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError:
                break
            data = response.json()

            comments = self._parse_comments(data)
            if not comments:
                break

            if include_reply_continuation:
                reply_continuations = self._extract_reply_continuations_for_comments(data)
                for comment in comments:
                    if comment["id"] in reply_continuations:
                        comment["reply_continuation_token"] = reply_continuations[comment["id"]]

            for comment in comments:
                if limit is not None and count >= limit:
                    return

                if since_date and comment.get("publish_date") and comment.get("publish_date") < since_date:
                    continuation_token = None
                    break

                yield comment
                count += 1
                if progress_callback:
                    progress_callback(count)

            if not continuation_token:
                break

            continuation_token = self._find_comment_page_continuation(data)

    def get_comment_replies(
        self,
        youtube_id: str,
        reply_continuation_token: str,
        limit: int = 100,
        progress_callback: Callable[[int], None] | None = None
    ):
        response = self._client.get(const.YOUTUBE_VIDEO_URL.format(youtube_id=youtube_id))
        response.raise_for_status()
        html_content = response.text

        api_key, context = self._find_api_key_and_context(html_content)

        fetched_count = 0
        current_token = reply_continuation_token
        processed_tokens = set()

        while current_token and fetched_count < limit:
            if current_token in processed_tokens:
                break
            processed_tokens.add(current_token)

            payload = {
                const.KEY_CONTEXT: context,
                const.KEY_CONTINUATION: current_token
            }

            response = self._client.post(f"{const.YOUTUBE_API_URL}?key={api_key}", json=payload)
            response.raise_for_status()
            reply_data = response.json()

            replies = self._parse_comments(reply_data)

            for reply in replies:
                if fetched_count < limit:
                    yield reply
                    fetched_count += 1
                else:
                    break

            if progress_callback:
                progress_callback(fetched_count)

            continuation = self._find_comment_page_continuation(reply_data)
            if continuation:
                 current_token = continuation
            else:
                 current_token = None

    def _find_comment_page_continuation(self, data: dict) -> str | None:
        continuations = list(self._search_dict(data, const.KEY_CONTINUATION_ITEM_RENDERER))
        if continuations:
            continuation_endpoint = continuations[-1].get(const.KEY_CONTINUATION_ENDPOINT, {})
            return continuation_endpoint.get(const.KEY_CONTINUATION_COMMAND, {}).get(const.KEY_TOKEN)
        return None

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
        data = self._regex_search(html_content, YT_INITIAL_DATA_RE)
        return json.loads(data) if data else {}

    def _parse_comments(self, data: dict) -> list[dict]:
        comments = []
        
        # Strategy 1: New structure with commentViewModel + mutations
        comment_view_models = []
        mutations = []
        
        # Collect commentViewModels from thread renderers  
        for renderer in self._search_dict(data, const.KEY_COMMENT_THREAD_RENDERER):
            if 'commentViewModel' in renderer:
                # Fix: Extract commentId from nested structure
                if 'commentViewModel' in renderer['commentViewModel']:
                    comment_view_models.append(renderer['commentViewModel'])
        
        # Collect mutations from frameworkUpdates
        for mutation in self._search_dict(data, 'mutations'):
            if isinstance(mutation, list):
                mutations.extend(mutation)
        
        # Match viewModels with mutations by commentId
        if comment_view_models and mutations:
            for i, view_model in enumerate(comment_view_models):
                # Fix: Extract commentId from nested structure
                if 'commentViewModel' in view_model:
                    inner_vm = view_model['commentViewModel']
                    comment_id = inner_vm.get('commentId')
                else:
                    comment_id = view_model.get('commentId')
                
                if comment_id:
                    # Find matching mutation
                    found_match = False
                    for j, mutation in enumerate(mutations):
                        if isinstance(mutation, dict) and 'payload' in mutation:
                            payload = mutation['payload']
                            if 'commentEntityPayload' in payload:
                                mutation_key = mutation.get('entityKey', '')
                                entity_key = payload['commentEntityPayload'].get('key', '')
                                
                                if mutation_key == comment_id or entity_key == comment_id:
                                    # Direct match found
                                    properties = payload['commentEntityPayload'].get('properties', {})
                                    if properties:
                                        comment_data = self._parse_new_comment_structure(properties, comment_id)
                                        if comment_data:
                                            comments.append(comment_data)
                                            found_match = True
                                        break
                                else:
                                    # Try to decode and match
                                    try:
                                        # URL decode first, then base64 decode
                                        decoded_key = urllib.parse.unquote(mutation_key)
                                        decoded_key = base64.b64decode(decoded_key).decode('utf-8', errors='ignore')
                                        # Find start of comment ID and extract it
                                        start_idx = decoded_key.find('Ug')
                                        if start_idx >= 0:
                                            decoded_key = decoded_key[start_idx:].split(' ')[0]
                                        
                                        decoded_entity = urllib.parse.unquote(entity_key) 
                                        decoded_entity = base64.b64decode(decoded_entity).decode('utf-8', errors='ignore')
                                        # Find start of comment ID and extract it
                                        start_idx = decoded_entity.find('Ug')
                                        if start_idx >= 0:
                                            decoded_entity = decoded_entity[start_idx:].split(' ')[0]
                                        
                                        if decoded_key == comment_id or decoded_entity == comment_id:
                                            # Parse the new structure
                                            properties = payload['commentEntityPayload'].get('properties', {})
                                            if properties:
                                                comment_data = self._parse_new_comment_structure(properties, comment_id)
                                                if comment_data:
                                                    comments.append(comment_data)
                                                    found_match = True
                                                break
                                    except Exception as e:
                                        continue  # Failed to decode, try next mutation
                    
                    if not found_match:
                        # Try direct parsing from properties in payload
                        for mutation in mutations:
                            if isinstance(mutation, dict) and 'payload' in mutation:
                                payload = mutation['payload']
                                if 'commentEntityPayload' in payload:
                                    properties = payload['commentEntityPayload'].get('properties', {})
                                    if properties and properties.get('commentId') == comment_id:
                                        comment_data = self._parse_new_comment_structure(properties, comment_id)
                                        if comment_data:
                                            comments.append(comment_data)
                                        break
        
        # Strategy 2: Try direct mutation parsing (without view models)
        if not comments:
            for mutation in mutations:
                if isinstance(mutation, dict) and 'payload' in mutation:
                    payload = mutation['payload']
                    if 'commentEntityPayload' in payload:
                        properties = payload['commentEntityPayload'].get('properties', {})
                        if properties and 'commentId' in properties:
                            comment_id = properties['commentId']
                            comment_data = self._parse_new_comment_structure(properties, comment_id)
                            if comment_data:
                                comments.append(comment_data)
        
        # Strategy 3: Legacy structure parsing
        if not comments:
            for renderer in self._search_dict(data, const.KEY_COMMENT_THREAD_RENDERER):
                comment_payload = renderer.get('comment', {}).get('commentRenderer', {})
                if comment_payload:
                    comments.append(self._parse_comment_payload(comment_payload))

            if not comments:
                for renderer in self._search_dict(data, const.KEY_COMMENT_RENDERER):
                     comments.append(self._parse_comment_payload(renderer))

        return comments

    def _parse_comment_payload(self, payload: dict) -> dict:
        author_badges = payload.get('authorBadges', [])
        pinned_badge = payload.get('pinnedCommentBadge', {})

        vote_count_text = payload.get('voteCount', {}).get('simpleText', '0')
        like_count = 0
        try:
            if vote_count_text.isdigit():
                like_count = int(vote_count_text)
            elif 'K' in vote_count_text.upper():
                like_count = int(float(vote_count_text.upper().replace('K', '')) * 1000)
            elif 'M' in vote_count_text.upper():
                like_count = int(float(vote_count_text.upper().replace('M', '')) * 1000000)
        except (ValueError, TypeError):
            like_count = 0

        published_time = payload.get("publishedTimeText", {}).get("runs", [{}])[0].get("text")
        if not published_time:
             published_time = payload.get("publishedTimeText", {}).get("simpleText")


        comment_data = {
            "id": payload.get("commentId"),
            "text": "".join([run["text"] for run in payload.get("contentText", {}).get("runs", [])]),
            "author": payload.get("authorText", {}).get("simpleText"),
            "author_channel_id": payload.get("authorEndpoint", {}).get("browseEndpoint", {}).get("browseId"),
            "author_avatar_url": "".join([thumb["url"] for thumb in payload.get("authorThumbnail", {}).get("thumbnails", [])]),
            "publish_date": date_utils.parse_human_readable_date(published_time) if published_time else None,
            "like_count": like_count,
            "reply_count": payload.get("replyCount", 0),
            "is_pinned": bool(pinned_badge),
            "author_badges": [badge["metadataBadgeRenderer"]["icon"]["iconType"] for badge in author_badges if "metadataBadgeRenderer" in badge],
            "is_reply": payload.get("isReply", False),
            "parent_id": payload.get("parentId")
        }
        return comment_data

    def _parse_new_comment_structure(self, properties: dict, comment_id: str) -> dict:
        """Parse the new YouTube comment structure from mutations payload"""
        try:
            # Extract text content - it appears to be a direct string
            text = properties.get('content', '')
            if isinstance(text, dict):
                # In case it's nested, try to extract
                text_content = text.get('content', {})
                if isinstance(text_content, dict):
                    text_runs = text_content.get('runs', [])
                    text = "".join([run.get('text', '') for run in text_runs])
                else:
                    text = str(text_content)
            else:
                text = str(text) if text else ''
            
            # Extract publish date
            published_time = properties.get('publishedTime', '')
            
            # For now, we'll use placeholder values for missing data
            # The actual author, like counts, etc. might be in the separate author/toolbar payloads
            comment_data = {
                "id": comment_id,
                "text": text,
                "author": "Unknown",  # Would need to get from author payload
                "author_channel_id": "",
                "author_avatar_url": "",
                "publish_date": date_utils.parse_human_readable_date(published_time) if published_time else None,
                "like_count": 0,  # Would need to get from toolbar payload
                "reply_count": 0,  # Would need to get from toolbar payload
                "is_pinned": False,
                "author_badges": [],
                "is_reply": False,
                "parent_id": None
            }
            
            return comment_data
            
        except Exception as e:
            return None
    
    def _parse_count_text(self, count_text: str) -> int:
        """Parse count text like '1.2K' or '500' into integer"""
        if not count_text or not isinstance(count_text, str):
            return 0
        
        try:
            count_text = count_text.strip().upper()
            if count_text.isdigit():
                return int(count_text)
            elif 'K' in count_text:
                return int(float(count_text.replace('K', '')) * 1000)
            elif 'M' in count_text:
                return int(float(count_text.replace('M', '')) * 1000000)
            else:
                return 0
        except (ValueError, TypeError):
            return 0

    def _find_api_key_and_context(self, html_content: str) -> tuple[str, dict]:
        ytcfg_str = self._regex_search(html_content, YT_CFG_RE)
        if not ytcfg_str:
            raise VideoUnavailableError("Could not find ytcfg")
        ytcfg = json.loads(ytcfg_str)
        return ytcfg["INNERTUBE_API_KEY"], ytcfg["INNERTUBE_CONTEXT"]

    def _get_sort_endpoints(self, initial_data):
        """
        Flexible method to find comment sorting endpoints using multiple strategies.
        This version handles the new YouTube API structure dynamically.
        """
        endpoints = {}
        if not initial_data:
            return endpoints
        
        # Strategy 1: Search for sortFilterSubMenuRenderer anywhere in the data
        for sort_menu in self._search_dict(initial_data, 'sortFilterSubMenuRenderer'):
            try:
                if 'subMenuItems' in sort_menu:
                    for item in sort_menu['subMenuItems']:
                        if 'title' in item and 'serviceEndpoint' in item:
                            label = item['title'].lower()
                            if 'continuationCommand' in item['serviceEndpoint']:
                                token = item['serviceEndpoint']['continuationCommand']['token']
                                endpoints[label] = (token, None, None)
            except (KeyError, TypeError):
                continue
                
        return endpoints

    def _extract_reply_continuations_for_comments(self, data: dict) -> dict:
        continuations = {}
        renderers = self._search_dict(data, const.KEY_COMMENT_THREAD_RENDERER)
        for renderer in renderers:
            if 'replies' in renderer:
                comment_id = renderer.get('comment', {}).get('commentRenderer', {}).get('commentId')
                if comment_id:
                    continuation_token = renderer['replies']['commentRepliesRenderer']['contents'][0]['continuationItemRenderer']['continuationEndpoint']['continuationCommand']['token']
                    continuations[comment_id] = continuation_token
        return continuations
