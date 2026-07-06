"""
Comment parser for extracting and structuring comment data from YouTube API responses.
"""

import logging
from typing import Any

from .date_utils import parse_relative_date_string

logger = logging.getLogger(__name__)


class CommentParser:
    """
    Handles extraction and parsing of comment data from YouTube API responses.
    Responsible for payload extraction, data mapping, and comment structuring.
    """

    def extract_reply_continuations(self, api_response: dict) -> dict[str, str]:
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

                    # Look for reply continuation token. YouTube moved the
                    # continuationItemRenderer from ``contents`` (older) to
                    # ``subThreads`` (current); check both so we work across
                    # the migration and against older cached responses.
                    if comment_id and "replies" in thread:
                        replies_renderer = thread["replies"].get(
                            "commentRepliesRenderer", {}
                        )
                        items = replies_renderer.get(
                            "subThreads"
                        ) or replies_renderer.get("contents") or []
                        for item in items:
                            token = (
                                item.get("continuationItemRenderer", {})
                                .get("continuationEndpoint", {})
                                .get("continuationCommand", {})
                                .get("token")
                            )
                            if token:
                                reply_tokens[comment_id] = token
                                logger.debug(
                                    "Found reply token for comment %s: %s...",
                                    comment_id,
                                    token[:50],
                                )
                                break

                for value in obj.values():
                    search_comment_threads(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_comment_threads(item)

        search_comment_threads(api_response)
        logger.debug(f"Extracted {len(reply_tokens)} reply continuation tokens")
        return reply_tokens

    def _parse_engagement_count(self, count_str: str | int | None) -> int:
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
            if count_str.endswith("K"):
                number_part = count_str[:-1]
                if "." in number_part:
                    return int(float(number_part) * 1000)
                else:
                    return int(number_part) * 1000

            # Handle 'M' suffix (millions)
            elif count_str.endswith("M"):
                number_part = count_str[:-1]
                if "." in number_part:
                    return int(float(number_part) * 1000000)
                else:
                    return int(number_part) * 1000000

            # Handle 'B' suffix (billions)
            elif count_str.endswith("B"):
                number_part = count_str[:-1]
                if "." in number_part:
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

    def extract_complete_comments(self, api_response: dict) -> list[dict[str, Any]]:
        """
        Extract complete comment data directly from commentEntityPayload.
        This approach gets all data (comment, author, toolbar) from a single payload.

        Args:
            api_response: API response data

        Returns:
            List of complete comment dictionaries
        """
        comments = []

        # C1: heart and pinned state don't live in commentEntityPayload
        # itself. Pre-scan the response once for both linkages:
        #   - engagementToolbarStateEntityPayload.heartState, keyed by
        #     its `key` == the comment's properties.toolbarStateKey;
        #   - commentViewModel entries carrying `pinnedText`, keyed by
        #     commentId.
        # Both were previously hardcoded False, which made every
        # is_hearted / is_pinned consumer (filters, example 28) a no-op.
        toolbar_states: dict[str, str] = {}
        pinned_ids: set[str] = set()

        def scan_states(obj):
            if isinstance(obj, dict):
                if "engagementToolbarStateEntityPayload" in obj:
                    payload = obj["engagementToolbarStateEntityPayload"]
                    key = payload.get("key")
                    if key:
                        toolbar_states[key] = payload.get("heartState", "")
                if "pinnedText" in obj and obj.get("commentId"):
                    pinned_ids.add(obj["commentId"])
                for value in obj.values():
                    scan_states(value)
            elif isinstance(obj, list):
                for item in obj:
                    scan_states(item)

        scan_states(api_response)

        def search_complete_comments(obj):
            if isinstance(obj, dict):
                if "commentEntityPayload" in obj:
                    payload = obj["commentEntityPayload"]

                    # Extract comment properties
                    properties = payload.get("properties", {})
                    comment_id = properties.get("commentId")

                    if not comment_id:
                        return

                    # Extract text content
                    content = properties.get("content", {})
                    text = content.get("content", "")

                    # Extract author data directly from payload
                    author_data = payload.get("author", {})
                    author_name = author_data.get("displayName", "Unknown")
                    author_channel_id = author_data.get("channelId", "")
                    author_avatar_url = author_data.get("avatarThumbnailUrl", "")
                    is_verified = author_data.get("isVerified", False)
                    is_creator = author_data.get("isCreator", False)

                    # Extract toolbar data directly from payload
                    toolbar_data = payload.get("toolbar", {})
                    like_count = self._parse_engagement_count(
                        toolbar_data.get("likeCountNotliked")
                        or toolbar_data.get("likeCountLiked")
                        or "0"
                    )
                    reply_count = self._parse_engagement_count(
                        toolbar_data.get("replyCount", "0")
                    )

                    # Extract time information
                    published_time = properties.get("publishedTime", "")
                    publish_date = None
                    if published_time:
                        try:
                            publish_date = parse_relative_date_string(published_time)
                        except Exception:
                            pass

                    # Extract other properties
                    reply_level = properties.get("replyLevel", 0)
                    is_reply = reply_level > 0

                    # C1: resolve heart/pinned from the pre-scanned maps.
                    toolbar_state_key = properties.get("toolbarStateKey")
                    is_hearted = (
                        toolbar_states.get(toolbar_state_key)
                        == "TOOLBAR_HEART_STATE_HEARTED"
                    )
                    is_pinned = comment_id in pinned_ids

                    comment = {
                        "id": comment_id,
                        "text": text,
                        "author": author_name,
                        "author_channel_id": author_channel_id,
                        "author_avatar_url": author_avatar_url,
                        "publish_date": publish_date,
                        "time_human": published_time,
                        # Option A: comments exist upstream ONLY as
                        # relative text — permanently approximate, to
                        # the day at best. publish_date_text mirrors
                        # time_human for cross-surface schema
                        # uniformity with videos/streams/playlists.
                        "publish_date_precision": (
                            "approximate" if publish_date else None
                        ),
                        "publish_date_text": published_time or None,
                        "time_parsed": None,
                        "like_count": like_count,
                        "reply_count": reply_count,
                        "is_hearted": is_hearted,
                        "is_reply": is_reply,
                        "is_pinned": is_pinned,
                        "paid_comment": None,
                        "author_badges": [],  # Can be extracted from author data if needed
                        "parent_id": None,  # For replies
                        "is_verified": is_verified,
                        "is_creator": is_creator,
                    }

                    comments.append(comment)

                for value in obj.values():
                    search_complete_comments(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_complete_comments(item)

        search_complete_comments(api_response)
        logger.debug(f"Extracted {len(comments)} complete comments directly")
        return comments
