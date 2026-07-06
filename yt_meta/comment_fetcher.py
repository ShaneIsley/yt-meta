"""
Main comment fetcher that orchestrates API client and parser for comprehensive comment extraction.
"""

import logging
from collections.abc import Callable, Iterator, MutableMapping
from datetime import date
from typing import Any

import httpx

from .comment_api_client import CommentAPIClient
from .comment_parser import CommentParser
from .exceptions import VideoUnavailableError
from .filtering import apply_comment_filters
from .utils import extract_video_id
from .validators import validate_filters

logger = logging.getLogger(__name__)


class CommentFetcher:
    """
    Main comment fetcher that combines API client and parser for complete comment extraction.
    Provides a clean interface for fetching YouTube comments with comprehensive metadata.
    """

    def __init__(
        self,
        timeout: int = 30,
        retries: int = 3,
        user_agent: str | None = None,
        session: httpx.Client | None = None,
        cache: MutableMapping | None = None,
    ):
        """Initialize the comment fetcher.

        Args:
            timeout, retries, user_agent: Used when constructing a
                self-owned httpx.Client. Ignored when ``session`` is
                injected.
            session: Optional httpx.Client to share with the surrounding
                Facade. YtMeta injects its main session here so the
                whole library uses one client (M1/L2).
            cache: Optional MutableMapping shared with the surrounding
                Facade. Used for caching watch-page parses under the
                ``video_initial:{video_id}`` key so VideoFetcher and
                CommentFetcher reuse each other's fetches.
        """
        self.api_client = CommentAPIClient(
            timeout=timeout,
            retries=retries,
            user_agent=user_agent,
            session=session,
            cache=cache,
        )
        self.parser = CommentParser()

    def close(self) -> None:
        """Close the underlying CommentAPIClient (which closes its
        httpx.Client). Idempotent. Replaces the prior ``__del__`` hook.
        """
        if hasattr(self, "api_client"):
            self.api_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_comments(
        self,
        video_id: str,
        limit: int | None = None,
        sort_by: str = "recent",
        since_date: date | None = None,
        progress_callback: Callable[[int], None] | None = None,
        include_reply_continuation: bool = False,
        filters: dict | None = None,
    ) -> Iterator[dict[str, Any]]:
        """
        Get comments from a YouTube video with comprehensive data extraction.

        Args:
            video_id: YouTube video ID or URL
            limit: Maximum number of comments to fetch
            sort_by: Sort order ("recent" — default, chronological; or "top" — YouTube's editorial ranking)
            since_date: Only fetch comments after this date (requires sort_by="recent"). The only filter that short-circuits pagination.
            progress_callback: Callback function called with comment count
            include_reply_continuation: Include reply continuation tokens for comments with replies
            filters: Optional dict of comment-level predicates applied after fetch. Operates on the in-memory comment list — does not reduce request count. See COMMENT_FILTER_KEYS in filtering.py for supported fields.

        Yields:
            Dict containing complete comment data, optionally including 'reply_continuation_token'
        """
        if since_date and sort_by != "recent":
            raise ValueError("`since_date` can only be used with `sort_by='recent'`")
        validate_filters(filters)
        # C4: the documented unbounded spellings are None and -1. A
        # negative limit reaching the loop guard (`comment_count < limit`)
        # would be instantly False and silently yield nothing.
        if limit is not None and limit < 0:
            limit = None

        video_id = extract_video_id(video_id)
        logger.info(f"Fetching comments for video: {video_id}")

        try:
            # Get initial video page data
            initial_data, ytcfg = self.api_client.get_initial_video_data(video_id)

            # Get comment sort endpoints with flexible detection
            sort_endpoints = self.api_client.get_sort_endpoints_flexible(
                initial_data, ytcfg
            )

            if not sort_endpoints:
                logger.warning("No comment sort endpoints found")
                return

            # Select appropriate endpoint
            continuation_token = self.api_client.select_sort_endpoint(
                sort_endpoints, sort_by
            )
            if not continuation_token:
                logger.warning(f"No continuation token found for sort_by='{sort_by}'")
                return

            # Fetch comments using continuation
            comment_count = 0
            seen_ids = set()
            # H4: consecutive pages that carried zero NEW comment ids. A
            # legitimate all-duplicate page can happen (sort_by='top'
            # re-rankings overlap window boundaries) — break only after
            # several in a row so a one-off doesn't silently truncate.
            # C5: "new" is measured PRE-filter — a page full of fresh
            # comments that all fail the user's filters is progress, not
            # an empty page. Counting post-filter survivors made a rare
            # filter (one specific author) truncate pagination after
            # EMPTY_PAGE_LIMIT filtered-out pages.
            consecutive_empty_pages = 0
            EMPTY_PAGE_LIMIT = 3

            # M-d: no inner try/except here. HTTP failures propagate as
            # httpx errors and are wrapped by the outer handler below;
            # parser bugs (KeyError from a YouTube shape change) surface
            # with their real stack trace instead of silently truncating
            # a complete-looking stream.
            while continuation_token and (limit is None or comment_count < limit):
                # Make API request for comments
                api_response = self.api_client.make_api_request(
                    continuation_token, ytcfg
                )

                if not api_response:
                    break

                # Extract complete comments directly (new approach)
                comments = self.parser.extract_complete_comments(api_response)

                # Extract reply continuation tokens if requested
                reply_tokens = {}
                if include_reply_continuation:
                    reply_tokens = self.parser.extract_reply_continuations(
                        api_response
                    )

                # Process comments
                found_new_ids = False
                for comment in comments:
                    if limit and comment_count >= limit:
                        break

                    if not comment or comment["id"] in seen_ids:
                        continue

                    # C5: record page progress BEFORE the user
                    # filters run. Filters are deterministic, so
                    # marking a filtered-out id as seen is safe —
                    # it would fail the same filters on any later
                    # page too.
                    seen_ids.add(comment["id"])
                    found_new_ids = True

                    # Apply date filtering
                    if since_date and comment.get("publish_date"):
                        if comment["publish_date"] < since_date:
                            continue

                    # Apply user-supplied predicate filters
                    if filters and not apply_comment_filters(comment, filters):
                        continue

                    comment_count += 1

                    # Add reply continuation token if available and requested
                    if include_reply_continuation and comment["id"] in reply_tokens:
                        comment["reply_continuation_token"] = reply_tokens[
                            comment["id"]
                        ]

                    if progress_callback:
                        progress_callback(comment_count)

                    yield comment

                # H4: tolerate N-1 consecutive all-duplicate pages
                # before breaking. The previous unconditional break
                # truncated results on any page that happened to
                # land all-duplicates (legitimate for 'top' sort)
                # AND masked H3's wrong-token bug.
                if found_new_ids:
                    consecutive_empty_pages = 0
                else:
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= EMPTY_PAGE_LIMIT:
                        break

                # Get next continuation token using API client
                continuation_token = self.api_client.extract_continuation_token(
                    api_response
                )


        except VideoUnavailableError:
            raise
        except (httpx.HTTPError, httpx.RequestError) as e:
            # M23: narrowed from `except Exception`. Programmer bugs
            # (KeyError from a code change in the parser, TypeError
            # from a wrong assumption) used to get wrapped as
            # "video unavailable" — misleading the user about the
            # actual cause. Now only genuine HTTP failures get the
            # VideoUnavailableError wrap; everything else surfaces
            # so the real stack trace is visible.
            logger.error(f"Error fetching comments: {e}")
            raise VideoUnavailableError(
                f"Could not fetch comments for video {video_id}: {e}"
            ) from e

    def get_comment_replies(
        self,
        video_id: str,
        reply_continuation_token: str,
        limit: int | None = None,
        progress_callback: Callable[[int], None] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """
        Get replies for a specific comment using its reply continuation token.

        Args:
            video_id: YouTube video ID or URL
            reply_continuation_token: Reply continuation token from a comment
            limit: Maximum number of replies to fetch
            progress_callback: Callback function called with reply count

        Yields:
            Dict containing complete reply data
        """
        # C4: same normalization as get_comments — -1 means unbounded.
        if limit is not None and limit < 0:
            limit = None
        video_id = extract_video_id(video_id)
        logger.info(f"Fetching replies for video: {video_id}")

        try:
            # Get initial video page data for ytcfg
            _, ytcfg = self.api_client.get_initial_video_data(video_id)

            # Fetch replies using continuation
            reply_count = 0
            seen_ids = set()
            continuation_token = reply_continuation_token

            while continuation_token and (limit is None or reply_count < limit):
                # M-d: no inner try/except — HTTP failures propagate to
                # the outer handler; parser bugs surface unwrapped.
                # Make API request for replies
                api_response = self.api_client.make_reply_request(
                    continuation_token, ytcfg
                )

                if not api_response:
                    break

                # Extract replies using the same direct extraction as main comments
                replies = self.parser.extract_complete_comments(api_response)
                replies_found = False

                for reply in replies:
                    if not reply or reply["id"] in seen_ids:
                        continue

                    if limit and reply_count >= limit:
                        break

                    # Mark as reply and set reply-specific properties
                    reply["is_reply"] = True
                    reply["reply_count"] = 0  # Replies don't have nested replies
                    reply["is_pinned"] = False  # Replies can't be pinned

                    seen_ids.add(reply["id"])
                    reply_count += 1
                    replies_found = True

                    if progress_callback:
                        progress_callback(reply_count)

                    yield reply

                if not replies_found:
                    break

                # Look for next continuation token for more replies
                continuation_token = self.api_client.extract_continuation_token(
                    api_response
                )

        except VideoUnavailableError:
            raise
        except httpx.HTTPError as e:
            # M-d: narrowed from `except Exception`, matching the M23
            # fix in get_comments — only genuine HTTP failures get the
            # VideoUnavailableError wrap; programmer bugs surface with
            # their real stack trace.
            logger.error(f"Error fetching replies: {e}")
            raise VideoUnavailableError(
                f"Could not fetch replies for video {video_id}: {e}"
            ) from e


def __getattr__(name):
    """Deprecated alias: ``BestCommentFetcher`` (the pre-0.4 class name).
    Emits DeprecationWarning on access; scheduled for removal in 0.9.0."""
    if name == "BestCommentFetcher":
        import warnings

        warnings.warn(
            "BestCommentFetcher is deprecated; use CommentFetcher. "
            "The alias will be removed in yt-meta 0.9.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return CommentFetcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
