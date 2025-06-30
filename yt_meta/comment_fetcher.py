import json
import re

import httpx

from . import constants as const

YT_CFG_RE = r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;'
YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'
YOUTUBE_VIDEO_URL = 'https://www.youtube.com/watch?v={youtube_id}'
YOUTUBE_API_URL = "https://www.youtube.com/youtubei/v1/next"
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'


class CommentFetcher:

    def __init__(self):
        self._client = httpx.Client(headers={'User-Agent': const.USER_AGENT})

    def get_comments(self, youtube_id: str, sort_by: str = "top"):
        """
        Fetch comments for a YouTube video.

        Args:
            youtube_id: The YouTube video ID
            sort_by: Comment sorting method ('top' or 'recent')
        """
        # 1. Get initial page
        response = self._client.get(const.YOUTUBE_VIDEO_URL.format(youtube_id=youtube_id))
        response.raise_for_status()
        html_content = response.text

        # 2. Extract initial data
        api_key, context = self._find_api_key_and_context(html_content)
        initial_data = self._extract_initial_data(html_content)

        # 3. Get the correct continuation token based on sort preference
        sort_endpoints = self._get_sort_endpoints(initial_data)
        if sort_by not in sort_endpoints:
            raise ValueError(f"Invalid sort_by value: '{sort_by}'. Available options are: {list(sort_endpoints.keys())}")

        current_continuation = sort_endpoints[sort_by]

        # 4. Use separate queues for comment pages and reply threads
        reply_continuations_queue = []

        # 5. Fetch all pages of the main, sorted comment thread
        while current_continuation:
            payload = {
                const.KEY_CONTEXT: context,
                const.KEY_CONTINUATION: current_continuation[const.KEY_CONTINUATION_COMMAND][const.KEY_TOKEN]
            }

            response = self._client.post(f"{const.YOUTUBE_API_URL}?key={api_key}", json=payload)
            response.raise_for_status()
            continuation_data = response.json()

            # Parse and yield comments from the current page
            comments = self._parse_comments(continuation_data)
            yield from comments

            # Find continuation for the next page of main comments
            current_continuation = self._find_comment_page_continuation(continuation_data)

            # Collect any 'show replies' continuations to process later
            reply_continuations_queue.extend(self._find_reply_thread_continuations(continuation_data))

        # 6. After fetching all main comments, fetch all replies for all threads
        processed_reply_tokens = set()

        while reply_continuations_queue:
            current_continuation = reply_continuations_queue.pop(0)
            token = current_continuation[const.KEY_CONTINUATION_COMMAND][const.KEY_TOKEN]

            if token in processed_reply_tokens:
                continue
            processed_reply_tokens.add(token)

            payload = {
                const.KEY_CONTEXT: context,
                const.KEY_CONTINUATION: token
            }

            response = self._client.post(f"{const.YOUTUBE_API_URL}?key={api_key}", json=payload)
            response.raise_for_status()
            reply_data = response.json()

            comments = self._parse_comments(reply_data)
            yield from comments

            # A reply thread itself can be paginated, so add its continuation back to the queue
            next_reply_page_continuation = self._find_comment_page_continuation(reply_data)
            if next_reply_page_continuation:
                reply_continuations_queue.append(next_reply_page_continuation)

    def _find_comment_page_continuation(self, data: dict) -> dict | None:
        """Finds the continuation for the next page of main comments."""
        actions = list(self._search_dict(data, const.KEY_RELOAD_CONTINUATION_ITEMS_COMMAND)) + \
                list(self._search_dict(data, const.KEY_APPEND_CONTINUATION_ITEMS_ACTION))

        for action in actions:
            continuation_items = action.get(const.KEY_CONTINUATION_ITEMS, [])
            if not continuation_items:
                continue

            # The continuation for the next comment page is typically the last item
            # and is a continuationItemRenderer.
            last_item = continuation_items[-1]
            if const.KEY_CONTINUATION_ITEM_RENDERER in last_item:
                endpoint = last_item[const.KEY_CONTINUATION_ITEM_RENDERER].get(const.KEY_CONTINUATION_ENDPOINT)
                if endpoint and const.KEY_CONTINUATION_COMMAND in endpoint:
                    return endpoint
        return None

    def _find_reply_thread_continuations(self, data: dict) -> list[dict]:
        """Finds all 'show replies' continuations in a response."""
        continuations = []

        # Look for commentThreadRenderers, which contain comments and their reply buttons
        thread_renderers = self._search_dict(data, const.KEY_COMMENT_THREAD_RENDERER)
        for thread in thread_renderers:
            if const.KEY_REPLIES in thread:
                replies_renderer = thread[const.KEY_REPLIES].get(const.KEY_COMMENT_REPLIES_RENDERER)
                if replies_renderer and const.KEY_CONTENTS in replies_renderer:
                    for item in replies_renderer[const.KEY_CONTENTS]:
                        continuation_item = item.get(const.KEY_CONTINUATION_ITEM_RENDERER)
                        if continuation_item:
                            endpoint = continuation_item.get(const.KEY_CONTINUATION_ENDPOINT)
                            if endpoint and const.KEY_CONTINUATION_COMMAND in endpoint:
                                continuations.append(endpoint)
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
        return json.loads(self._regex_search(html_content, const.YT_INITIAL_DATA_RE, default='{}'))

    def _find_continuation_token(self, data: dict) -> str | None:
        # First try the engagement panels (where comments are located on initial page load)
        engagement_panels = data.get(const.KEY_ENGAGEMENT_PANELS, [])
        for panel in engagement_panels:
            if const.KEY_ENGAGEMENT_PANEL_SECTION_LIST_RENDERER in panel:
                # Check if this is the comments panel
                header = panel[const.KEY_ENGAGEMENT_PANEL_SECTION_LIST_RENDERER].get(const.KEY_HEADER, {})
                title_header = header.get(const.KEY_ENGAGEMENT_PANEL_TITLE_HEADER_RENDERER, {})
                title = title_header.get(const.KEY_TITLE, {}).get(const.KEY_RUNS, [{}])[0].get(const.KEY_TEXT, '')

                if 'comments' in title.lower():
                    # Look for continuation in the content
                    content = panel[const.KEY_ENGAGEMENT_PANEL_SECTION_LIST_RENDERER].get(const.KEY_CONTENT, {})
                    continuations = self._search_dict(content, const.KEY_CONTINUATION_ENDPOINT)
                    for continuation in continuations:
                        if continuation:
                            token = continuation.get(const.KEY_CONTINUATION_COMMAND, {}).get(const.KEY_TOKEN)
                            if token:
                                return token

        # Check onResponseReceivedEndpoints for continuation items
        endpoints = data.get(const.KEY_ON_RESPONSE_RECEIVED_ENDPOINTS, [])
        for endpoint in endpoints:
            # Check appendContinuationItemsAction
            if const.KEY_APPEND_CONTINUATION_ITEMS_ACTION in endpoint:
                action = endpoint[const.KEY_APPEND_CONTINUATION_ITEMS_ACTION]
                items = action.get(const.KEY_CONTINUATION_ITEMS, [])
                for item in items:
                    if const.KEY_CONTINUATION_ITEM_RENDERER in item:
                        renderer = item[const.KEY_CONTINUATION_ITEM_RENDERER]
                        if const.KEY_CONTINUATION_ENDPOINT in renderer:
                            cont_endpoint = renderer[const.KEY_CONTINUATION_ENDPOINT]
                            token = cont_endpoint.get(const.KEY_CONTINUATION_COMMAND, {}).get(const.KEY_TOKEN)
                            if token:
                                return token

            # Check reloadContinuationItemsCommand
            if const.KEY_RELOAD_CONTINUATION_ITEMS_COMMAND in endpoint:
                command = endpoint[const.KEY_RELOAD_CONTINUATION_ITEMS_COMMAND]
                items = command.get(const.KEY_CONTINUATION_ITEMS, [])
                for item in items:
                    if const.KEY_CONTINUATION_ITEM_RENDERER in item:
                        renderer = item[const.KEY_CONTINUATION_ITEM_RENDERER]
                        if const.KEY_CONTINUATION_ENDPOINT in renderer:
                            cont_endpoint = renderer[const.KEY_CONTINUATION_ENDPOINT]
                            token = cont_endpoint.get(const.KEY_CONTINUATION_COMMAND, {}).get(const.KEY_TOKEN)
                            if token:
                                return token

        # Fallback to the original search method for any other continuation structures
        continuations = self._search_dict(data, const.KEY_CONTINUATION_ENDPOINT)
        for continuation in continuations:
            if continuation:
                 token = continuation.get(const.KEY_CONTINUATION_COMMAND, {}).get(const.KEY_TOKEN)
                 if token:
                     return token
        return None

    def _parse_comments(self, data: dict) -> list[dict]:
        comments = []

        # Comment data in continuation responses is delivered via frameworkUpdates,
        # which contains a batch of mutations to apply to the page's data entities.
        framework = data.get(const.KEY_FRAMEWORK_UPDATES, {})
        entity_batch = framework.get(const.KEY_ENTITY_BATCH_UPDATE, {})
        mutations = entity_batch.get(const.KEY_MUTATIONS, [])

        for mutation in mutations:
            if const.KEY_PAYLOAD in mutation and const.KEY_COMMENT_ENTITY_PAYLOAD in mutation[const.KEY_PAYLOAD]:
                payload = mutation[const.KEY_PAYLOAD][const.KEY_COMMENT_ENTITY_PAYLOAD]
                comments.append(self._parse_comment_payload(payload))

        # If we found comments in frameworkUpdates, return them
        if comments:
            return comments

        # Fallback for initial page loads where comments might be in a different structure
        comment_payloads = self._search_dict(data, const.KEY_COMMENT_ENTITY_PAYLOAD)
        for payload in comment_payloads:
            comments.append(self._parse_comment_payload(payload))

        return comments

    def _parse_comment_payload(self, payload: dict) -> dict:
        """
        Parses a single `commentEntityPayload` from the YouTube API into our
        standardized comment format.

        The `payload` is a dictionary containing all information about a single
        comment, including its text, author, and engagement data.
        """
        # `properties` contains the core text and metadata of the comment itself.
        properties = payload.get(const.KEY_PROPERTIES, {})
        # `author` contains information about the commenter (name, channel ID, avatar).
        author = payload.get(const.KEY_AUTHOR, {})
        # `toolbar` contains engagement data like likes and reply count.
        toolbar = payload.get(const.KEY_TOOLBAR, {})

        # The main comment text.
        text = properties.get(const.KEY_CONTENT, {}).get(const.KEY_CONTENT, "")

        author_badges = []
        if const.KEY_AUTHOR_BADGES in author:
            for badge in author[const.KEY_AUTHOR_BADGES]:
                if const.KEY_CHANNEL_RENDERER in badge[const.KEY_BADGE_RENDERER][const.KEY_NAVIGATION_ENDPOINT][const.KEY_BROWSE_ENDPOINT]:
                    author_badges.append(badge[const.KEY_BADGE_RENDERER][const.KEY_ICON][const.KEY_ICON_TYPE])
        elif const.KEY_OWNER_BADGES in author:
            for badge in author[const.KEY_OWNER_BADGES]:
                author_badges.append(badge[const.KEY_METADATA_BADGE_RENDERER][const.KEY_ICON][const.KEY_ICON_TYPE])
        elif const.KEY_IS_VERIFIED in author and author[const.KEY_IS_VERIFIED]:
            author_badges.append("VERIFIED")

        is_by_owner = author.get(const.KEY_IS_CREATOR, False) or 'CREATOR' in author_badges

        like_count_str = str(toolbar.get('likeCountLiked') or toolbar.get('likeCountNotliked', 0))
        likes = int(like_count_str) if like_count_str.isdigit() else 0

        reply_count_str = str(toolbar.get(const.KEY_REPLY_COUNT, 0))
        replies = int(reply_count_str) if reply_count_str.isdigit() else 0

        return {
            "id": properties.get("commentId"),
            "text": text,
            "author": author.get(const.KEY_DISPLAY_NAME),
            "author_channel_id": author.get(const.KEY_CHANNEL_ID),
            "author_avatar_url": author.get(const.KEY_AVATAR_THUMBNAIL_URL),
            "likes": likes,
            "is_reply": properties.get("replyLevel", 0) > 0,
            "is_by_owner": is_by_owner,
            "is_pinned": properties.get(const.KEY_IS_PINNED, False),
            "is_hearted_by_owner": toolbar.get("heartIsActive", False),
            "reply_count": replies,
            "published_time": properties.get(const.KEY_PUBLISHED_TIME, ""),
            "author_badges": author_badges,
        }

    def _find_api_key_and_context(self, html_content: str) -> tuple[str, dict]:
        """Extracts the API key and Innertube context from the page source."""
        ytcfg_str = self._regex_search(html_content, const.YT_CFG_RE, default='{}')
        ytcfg = json.loads(ytcfg_str)
        api_key = ytcfg.get(const.KEY_INNERTUBE_API_KEY)
        context = ytcfg.get(const.KEY_INNERTUBE_CONTEXT)
        return api_key, context

    def _get_sort_endpoints(self, data: dict) -> dict:
        """Finds the 'Top comments' and 'Newest first' continuation tokens."""
        endpoints = {}
        try:
            # First, try the direct navigation path, which is most reliable.
            engagement_panel = next(self._search_dict(data, const.KEY_ENGAGEMENT_PANEL_SECTION_LIST_RENDERER))
            sort_menu = engagement_panel[const.KEY_HEADER][const.KEY_ENGAGEMENT_PANEL_TITLE_HEADER_RENDERER][const.KEY_MENU][const.KEY_SORT_FILTER_SUB_MENU_RENDERER]
        except (StopIteration, KeyError):
            # If direct navigation fails, fall back to a generic search for the sort menu.
            # This is less reliable but handles variations in the initial data structure.
            sort_menu = next(self._search_dict(data, const.KEY_SORT_FILTER_SUB_MENU_RENDERER), None)
            if not sort_menu:
                # If we truly can't find the sort menu, we cannot offer sorting.
                # As a last resort, find the default continuation token for the page
                # so that at least 'top' comments can be fetched.
                token = self._find_continuation_token(data)
                if token:
                    endpoints['top'] = {const.KEY_CONTINUATION_COMMAND: {const.KEY_TOKEN: token}}
                return endpoints

        # Once the sort menu is found, extract the endpoints from it.
        for item in sort_menu.get(const.KEY_SUB_MENU_ITEMS, []):
            title = item.get(const.KEY_TITLE, "").lower()
            endpoint = item.get(const.KEY_SERVICE_ENDPOINT)
            if not endpoint:
                continue

            if "top" in title:
                endpoints["top"] = endpoint
            elif "newest" in title:
                endpoints["recent"] = endpoint
        
        if not endpoints:
             raise ValueError("Could not find sort endpoints in initial data.")
        
        return endpoints
