"""
Main comment fetcher that orchestrates API client and parser for comprehensive comment extraction.
"""

import logging
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

from .comment_api_client import CommentAPIClient
from .comment_parser import CommentParser
from .exceptions import VideoUnavailableError
from .utils import extract_video_id

logger = logging.getLogger(__name__)


class CommentFetcher:
    """
    Main comment fetcher that combines API client and parser for complete comment extraction.
    Provides a clean interface for fetching YouTube comments with comprehensive metadata.
    """

    def __init__(
        self, timeout: int = 30, retries: int = 3, user_agent: str | None = None
    ):
        """Initialize the comment fetcher with HTTP client configuration."""
        self.api_client = CommentAPIClient(timeout, retries, user_agent)
        self.parser = CommentParser()

    def __del__(self):
        """Cleanup resources on destruction."""
        if hasattr(self, "api_client"):
            del self.api_client

    def get_comments(
        self,
        video_id: str,
        limit: int | None = None,
        sort_by: str = "top",
        since_date: date | None = None,
        progress_callback: Callable[[int], None] | None = None,
        include_reply_continuation: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """
        Get comments from a YouTube video with comprehensive data extraction.

        Args:
            video_id: YouTube video ID or URL
            limit: Maximum number of comments to fetch
            sort_by: Sort order ("top" or "recent")
            since_date: Only fetch comments after this date (requires sort_by="recent")
            progress_callback: Callback function called with comment count
            include_reply_continuation: Include reply continuation tokens for comments with replies

        Yields:
            Dict containing complete comment data, optionally including 'reply_continuation_token'
        """
        # Validate parameters
        if since_date and sort_by != "recent":
            raise ValueError("`since_date` can only be used with `sort_by='recent'`")

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

            while continuation_token and (limit is None or comment_count < limit):
                try:
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
                    found_comments = False
                    for comment in comments:
                        if limit and comment_count >= limit:
                            break

                        if not comment or comment["id"] in seen_ids:
                            continue

                        # Apply date filtering
                        if since_date and comment.get("publish_date"):
                            if comment["publish_date"] < since_date:
                                continue

                        seen_ids.add(comment["id"])
                        comment_count += 1
                        found_comments = True

                        # Add reply continuation token if available and requested
                        if include_reply_continuation and comment["id"] in reply_tokens:
                            comment["reply_continuation_token"] = reply_tokens[
                                comment["id"]
                            ]

                        if progress_callback:
                            progress_callback(comment_count)

                        yield comment

                    if not found_comments:
                        break

                    # Get next continuation token using API client
                    continuation_token = self.api_client.extract_continuation_token(
                        api_response
                    )

                except Exception as e:
                    logger.error(f"Error processing comment batch: {e}")
                    break

        except VideoUnavailableError:
            raise
        except Exception as e:
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
                try:
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

                except Exception as e:
                    logger.error(f"Error processing reply batch: {e}")
                    break

        except VideoUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Error fetching replies: {e}")
            raise VideoUnavailableError(
                f"Could not fetch replies for video {video_id}: {e}"
            ) from e


# Maintain backward compatibility with the old class name
BestCommentFetcher = CommentFetcher
