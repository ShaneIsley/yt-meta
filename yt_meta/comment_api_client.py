"""
Comment API client for handling HTTP operations and YouTube API interaction.
"""

import json
import logging
import re
from collections.abc import MutableMapping

import httpx

from ._retry import request_with_retries
from .caching import DummyCache
from .exceptions import VideoUnavailableError
from .utils import _deep_get

logger = logging.getLogger(__name__)


class CommentAPIClient:
    """
    Handles HTTP operations and YouTube API interaction for comment fetching.
    Responsible for endpoint detection, API requests, and data retrieval.
    """

    def __init__(
        self,
        timeout: int = 30,
        retries: int = 3,
        user_agent: str | None = None,
        session: httpx.Client | None = None,
        cache: MutableMapping | None = None,
    ):
        """Initialize the API client.

        Args:
            timeout: HTTP timeout for self-owned sessions. Ignored when
                ``session`` is injected.
            retries: Reserved for future retry-wrapper work (H9).
            user_agent: User-Agent for self-owned sessions. Ignored when
                ``session`` is injected.
            session: An ``httpx.Client`` to use instead of constructing
                a new one. YtMeta injects its main session here under
                M1/L2 so the whole library shares one client and the
                whole watch-page cache stays consistent. When injected,
                this object does NOT own the session (close() leaves it
                alone — lifecycle stays with the injector).
            cache: A ``MutableMapping`` for caching watch-page parse
                results under the shared ``video_initial:{video_id}``
                key. YtMeta injects its main cache here so comment
                fetches reuse any prior watch-page fetch done by
                VideoFetcher (and vice versa, eventually). Defaults to
                a no-op ``DummyCache``.
        """
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        if session is not None:
            self.client = session
            self._owns_client = False
        else:
            self.client = httpx.Client(
                timeout=timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            )
            self._owns_client = True

        self.cache = cache if cache is not None else DummyCache()

    def close(self) -> None:
        """Close the underlying httpx.Client IF we own it. Injected
        sessions are left alone — the injector owns the lifecycle.
        Idempotent. Replaces the prior ``__del__`` hook which was
        unreliable at interpreter shutdown and on reference cycles.
        """
        if hasattr(self, "client") and getattr(self, "_owns_client", True):
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_initial_video_data(self, video_id: str) -> tuple[dict, dict]:
        """Get initial video page data and ytcfg.

        Caches the (initial_data, ytcfg) parse under
        ``video_initial:{video_id}`` — a shared key so that
        VideoFetcher and CommentFetcher reuse each other's watch-page
        fetches (M1/L2).
        """
        cache_key = f"video_initial:{video_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            response = self.client.get(url)
            response.raise_for_status()
            html_content = response.text
        except (httpx.HTTPError, httpx.RequestError) as e:
            # M23: narrow to httpx errors. Anything else (KeyError,
            # programmer bug) surfaces unwrapped so the actual cause
            # isn't misleadingly reported as "video unavailable".
            raise VideoUnavailableError(f"Could not load video page: {e}") from e

        ytcfg = self._extract_ytcfg(html_content)
        initial_data = self._extract_initial_data(html_content)
        result = (initial_data, ytcfg)
        self.cache[cache_key] = result
        return result

    def _extract_ytcfg(self, html_content: str) -> dict:
        """Extract ytcfg configuration from HTML."""
        ytcfg_pattern = r"ytcfg\.set\s*\(\s*({.+?})\s*\)"
        match = re.search(ytcfg_pattern, html_content, re.DOTALL)

        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return {}

    def _extract_initial_data(self, html_content: str) -> dict:
        """Extract ytInitialData from HTML."""
        initial_data_pattern = r"var\s+ytInitialData\s*=\s*({.+?});"
        match = re.search(initial_data_pattern, html_content, re.DOTALL)

        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return {}

    def get_sort_endpoints_flexible(
        self, initial_data: dict, ytcfg: dict
    ) -> dict[str, str]:
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
                            endpoint = (
                                item.get("serviceEndpoint", {})
                                .get("continuationCommand", {})
                                .get("token")
                            )
                            if endpoint:
                                endpoints[title] = endpoint
                                logger.debug(
                                    f"Added endpoint: {title} -> {endpoint[:50]}..."
                                )

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

        logger.info(
            f"Found {len(endpoints)} comment endpoints: {list(endpoints.keys())}"
        )
        return endpoints

    def _is_comment_panel(self, panel: dict) -> bool:
        """Determine if an engagement panel is related to comments."""
        panel_str = json.dumps(panel).lower()
        return any(
            keyword in panel_str for keyword in ["comment", "discussion", "engagement"]
        )

    def _extract_endpoints_from_panel(self, panel: dict, endpoints: dict):
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

    def select_sort_endpoint(
        self, endpoints: dict[str, str], sort_by: str
    ) -> str | None:
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
                    logger.info(
                        f"Selected endpoint: {endpoint_name} for sort_by='{sort_by}'"
                    )
                    return token

        # Fallback to first available endpoint
        if endpoints:
            first_endpoint = list(endpoints.keys())[0]
            token = endpoints[first_endpoint]
            logger.info(
                f"Fallback to endpoint: {first_endpoint} for sort_by='{sort_by}'"
            )
            return token

        return None

    def make_api_request(self, continuation_token: str, ytcfg: dict) -> dict | None:
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

        payload = {"context": context, "continuation": continuation_token}

        try:
            # H9: wire the previously-ignored ``retries`` constructor
            # param through the actual retry/backoff helper.
            response = request_with_retries(
                lambda: self.client.post(url, json=payload), retries=self.retries
            )
            return response.json()

        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None

    def extract_continuation_token(self, api_response: dict) -> str | None:
        """Extract the next-page continuation token from a comment API response.

        Walks the documented ``onResponseReceivedEndpoints`` path
        explicitly. Each entry wraps its items in either:

          - ``reloadContinuationItemsCommand`` (first-page response), or
          - ``appendContinuationItemsAction`` (subsequent pages)

        Both have a ``continuationItems`` list. The next-page token is
        in the LAST ``continuationItemRenderer`` in that list (earlier
        items are comment threads, which themselves contain nested
        reply continuation tokens we MUST NOT pick up).

        H3 history: the previous implementation did a free-form DFS
        and returned the first token whose value matched a fuzzy
        substring check (``_is_comment_token``). That check accepted
        any token containing 'replies', which YouTube routinely embeds
        inside ``commentRepliesRenderer`` subtrees per thread. DFS
        visited those nested tokens before the top-level next-page
        token, so the function returned a reply continuation instead.
        The next API call then fetched replies for an already-seen
        thread, every id was a duplicate, and the (pre-H4) early-break
        silently truncated the comment stream.

        Returns None if no next-page token is present (end of stream).
        """
        if not isinstance(api_response, dict):
            return None
        endpoints = api_response.get("onResponseReceivedEndpoints") or []
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                continue
            items_wrapper = endpoint.get(
                "reloadContinuationItemsCommand"
            ) or endpoint.get("appendContinuationItemsAction")
            if not items_wrapper:
                continue
            items = items_wrapper.get("continuationItems") or []
            # The next-page token is the LAST continuationItemRenderer.
            # Iterate in reverse so we find it without scanning every
            # thread, and so we never see a comment thread first.
            for item in reversed(items):
                if not isinstance(item, dict):
                    continue
                renderer = item.get("continuationItemRenderer")
                if not renderer:
                    continue
                token = _deep_get(
                    renderer,
                    "continuationEndpoint.continuationCommand.token",
                )
                if token:
                    return token
        return None

    def make_reply_request(
        self, reply_continuation_token: str, ytcfg: dict
    ) -> dict | None:
        """
        Make API request to get reply data using reply continuation token.

        Args:
            reply_continuation_token: Reply continuation token
            ytcfg: YouTube configuration data

        Returns:
            API response data containing replies or None if failed
        """
        api_key = ytcfg.get("INNERTUBE_API_KEY")
        if not api_key:
            logger.error("No API key found in ytcfg")
            return None

        url = f"https://www.youtube.com/youtubei/v1/next?key={api_key}"

        context = ytcfg.get("INNERTUBE_CONTEXT", {})

        payload = {"context": context, "continuation": reply_continuation_token}

        try:
            response = request_with_retries(
                lambda: self.client.post(url, json=payload), retries=self.retries
            )
            return response.json()

        except Exception as e:
            logger.error(f"Reply API request failed: {e}")
            return None
