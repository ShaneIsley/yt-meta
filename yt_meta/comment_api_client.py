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
from .exceptions import MetadataParsingError, VideoUnavailableError
from .parsing import extract_and_parse_json, find_comment_sort_tokens
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
        ``video_initial:{video_id}``, in the cache shared across the
        YtMeta facade (M1/L2), so repeated comment and reply fetches for
        a video reuse one watch-page request. VideoFetcher does NOT read
        this key: it caches its own parsed record under
        ``video_meta:{video_id}``, so fetching a video's metadata and its
        comments still downloads the watch page twice.
        """
        cache_key = f"video_initial:{video_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            # C3: retry transient failures on the initial watch-page GET,
            # matching the continuation POSTs which were already wrapped.
            response = request_with_retries(
                lambda: self.client.get(url), retries=self.retries
            )
            html_content = response.text
        except httpx.HTTPError as e:
            # M23: narrow to httpx errors. Anything else (KeyError,
            # programmer bug) surfaces unwrapped so the actual cause
            # isn't misleadingly reported as "video unavailable".
            raise VideoUnavailableError(f"Could not load video page: {e}") from e

        ytcfg = self._extract_ytcfg(html_content)
        initial_data = self._extract_initial_data(html_content)
        result = (initial_data, ytcfg)
        # Cache only a usable parse. A consent page or a markup change
        # yields no API key; caching that made every comment fetch for
        # the video return nothing, silently, for the whole cache TTL.
        if initial_data and ytcfg.get("INNERTUBE_API_KEY"):
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
        """Extract ytInitialData from HTML (either page format; see
        parsing.extract_and_parse_json). Returns {} when absent."""
        return extract_and_parse_json(html_content, "ytInitialData") or {}

    def get_sort_endpoints_flexible(
        self, initial_data: dict, ytcfg: dict | None = None
    ) -> dict[str, str]:
        """Comment sort tokens on the watch page, keyed "top" / "recent"
        (see parsing.find_comment_sort_tokens). ``ytcfg`` is unused and
        kept for call compatibility."""
        endpoints = find_comment_sort_tokens(initial_data or {})
        logger.info(f"Found comment sort options: {list(endpoints)}")
        return endpoints

    def select_sort_endpoint(
        self, endpoints: dict[str, str], sort_by: str, allow_fallback: bool = True
    ) -> str | None:
        """
        Select the appropriate endpoint based on the requested sort order.

        Args:
            endpoints: Dictionary of available endpoints
            sort_by: Requested sort order ("top" or "recent"); anything
                else raises ValueError
            allow_fallback: When no endpoint matches sort_by, return the
                first endpoint (True) or None (False)

        Returns:
            Continuation token for the requested sort order
        """
        if sort_by not in ("top", "recent"):
            raise ValueError(f"sort_by must be 'recent' or 'top', got {sort_by!r}")
        if not endpoints:
            return None

        # Mapping of sort preferences to endpoint keywords
        if sort_by == "top":
            preferences = ["top comments", "top", "best comments", "best"]
        else:
            preferences = ["newest first", "newest", "recent", "new comments", "latest"]

        # Try to find exact matches first
        for pref in preferences:
            for endpoint_name, token in endpoints.items():
                if pref.lower() in endpoint_name.lower():
                    logger.info(
                        f"Selected endpoint: {endpoint_name} for sort_by='{sort_by}'"
                    )
                    return token

        # No named match: fall back to the first endpoint (usually YouTube's
        # default, top-ranked order) unless the caller needs the order
        # guaranteed, as since_date does.
        if not allow_fallback:
            return None
        first_endpoint = next(iter(endpoints))
        logger.warning(
            f"No '{sort_by}' comment ordering found; falling back to "
            f"'{first_endpoint}'. Comments may not be in the requested order."
        )
        return endpoints[first_endpoint]

    def make_api_request(self, continuation_token: str, ytcfg: dict) -> dict | None:
        """
        Make API request to get comment data using continuation token.

        Args:
            continuation_token: Token for the API request
            ytcfg: YouTube configuration data

        Returns:
            API response data. Raises MetadataParsingError when ytcfg
            has no API key.
        """
        api_key = ytcfg.get("INNERTUBE_API_KEY")
        if not api_key:
            # Raise rather than return None: the pagination loops read
            # None as end-of-stream, so a missing key looked like a video
            # with zero comments.
            raise MetadataParsingError(
                "No INNERTUBE_API_KEY in the watch page config (consent page "
                "or a YouTube markup change); cannot request comments."
            )

        url = f"https://www.youtube.com/youtubei/v1/next?key={api_key}"

        context = ytcfg.get("INNERTUBE_CONTEXT", {})

        payload = {"context": context, "continuation": continuation_token}

        # H9: wire the previously-ignored ``retries`` constructor param
        # through the actual retry/backoff helper. M-d: no blanket
        # except — a persistent HTTP failure used to become None, which
        # the pagination loop treated as a normal end-of-stream (silent
        # truncation). Let it propagate; CommentFetcher wraps httpx
        # errors as VideoUnavailableError.
        response = request_with_retries(
            lambda: self.client.post(url, json=payload), retries=self.retries
        )
        return self._json(response)

    @staticmethod
    def _json(response) -> dict:
        """response.json(), with a non-JSON body (HTML error page, a
        truncated response) raised as MetadataParsingError instead of a
        bare JSONDecodeError."""
        try:
            return response.json()
        except ValueError as e:
            raise MetadataParsingError(
                f"Comment API response was not valid JSON: {e}"
            ) from e

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

        M-c: the renderer carries its token in one of two forms —
        ``continuationEndpoint.continuationCommand.token`` (comment
        pages) or ``button.buttonRenderer.command.continuationCommand
        .token`` (reply "Show more replies" pages). Only the first was
        handled, so reply pagination silently stopped after page one.
        Verified against a live-captured reply page
        (tests/fixtures/comment_reply_page_with_continuation.json).

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
                ) or _deep_get(
                    renderer,
                    "button.buttonRenderer.command.continuationCommand.token",
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
            API response data containing replies. Raises
            MetadataParsingError when ytcfg has no API key.
        """
        api_key = ytcfg.get("INNERTUBE_API_KEY")
        if not api_key:
            # Raise rather than return None: the pagination loops read
            # None as end-of-stream, so a missing key looked like a video
            # with zero comments.
            raise MetadataParsingError(
                "No INNERTUBE_API_KEY in the watch page config (consent page "
                "or a YouTube markup change); cannot request comments."
            )

        url = f"https://www.youtube.com/youtubei/v1/next?key={api_key}"

        context = ytcfg.get("INNERTUBE_CONTEXT", {})

        payload = {"context": context, "continuation": reply_continuation_token}

        # M-d: same as make_api_request — HTTP failures propagate.
        response = request_with_retries(
            lambda: self.client.post(url, json=payload), retries=self.retries
        )
        return self._json(response)
