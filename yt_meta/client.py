# yt_meta/client.py

import logging
from collections.abc import Callable, Generator, MutableMapping
from datetime import date, datetime
from typing import Dict, List

from httpx import Client

from .caching import DummyCache, SQLiteCache
from .comment_fetcher import CommentFetcher
from .date_utils import parse_relative_date_string
from .fetchers import ChannelFetcher, PlaylistFetcher, VideoFetcher
from .transcript_fetcher import TranscriptFetcher
from .utils import extract_video_id

logger = logging.getLogger(__name__)


class YtMeta:
    """
    A client for fetching metadata for YouTube videos, channels, playlists, and comments.
    This class acts as a Facade, delegating calls to specialized fetcher classes.
    """

    def __init__(
        self,
        cache_path: str | None = None,
        cache: MutableMapping | None = None,
        cache_ttl_seconds: int = 86400,
    ):
        """
        Initializes the yt-meta client.

        Args:
            cache_path: If provided, the path to a SQLite file for persistent,
                        on-disk caching.
            cache: Any MutableMapping (e.g. a plain ``dict`` for an
                   in-memory cache, or ``diskcache.Cache`` for a persistent
                   one). Takes precedence over ``cache_path``. If both are
                   ``None`` (the default), caching is disabled.
            cache_ttl_seconds: TTL applied to entries in the built-in
                   SQLiteCache (used when ``cache_path`` is given). Default
                   is 86400 (1 day). Ignored when ``cache`` is supplied —
                   inject a cache with the TTL semantics you want.
        """
        self.session = Client(headers={"Accept-Language": "en-US,en;q=0.5"})
        if cache is not None:
            self.cache = cache
            logger.info(f"Using injected cache: {type(cache).__name__}")
        elif cache_path:
            self.cache = SQLiteCache(path=cache_path, ttl_seconds=cache_ttl_seconds)
            logger.info(
                f"Using SQLite cache at: {cache_path} (TTL {cache_ttl_seconds}s)"
            )
        else:
            self.cache = DummyCache()
            logger.info("Caching is disabled.")

        self._video_fetcher = VideoFetcher(session=self.session, cache=self.cache)
        self._channel_fetcher = ChannelFetcher(
            session=self.session, cache=self.cache, video_fetcher=self._video_fetcher
        )
        self._playlist_fetcher = PlaylistFetcher(
            session=self.session, cache=self.cache, video_fetcher=self._video_fetcher
        )
        # M1/L2: inject the main session and cache so the comment
        # subsystem shares resources with the rest of the Facade
        # instead of constructing its own httpx.Client and bypassing
        # the cache.
        self._comment_fetcher = CommentFetcher(
            session=self.session, cache=self.cache
        )
        self._transcript_fetcher = TranscriptFetcher()

    @property
    def comment_fetcher(self) -> CommentFetcher:
        return self._comment_fetcher

    def close(self) -> None:
        """Release all resources owned by this client — the main
        httpx.Client and the SQLite cache connection (when
        ``cache_path`` was given).

        Idempotent. Safe to call multiple times. Prefer the context
        manager pattern (``with YtMeta() as client:``) which calls this
        automatically on exit; explicit ``close()`` works for code that
        doesn't structure around context managers.

        Since M1/L2 the comment subsystem shares this client's session
        and cache, so there's nothing extra to close on that side. The
        comment_fetcher.close() call is kept as a no-op safety net
        (the CommentAPIClient knows not to close an injected session).
        """
        if hasattr(self, "session"):
            self.session.close()
        if hasattr(self, "_comment_fetcher"):
            self._comment_fetcher.close()
        if hasattr(self, "cache"):
            close = getattr(self.cache, "close", None)
            if callable(close):
                close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def clear_cache(self, prefix: str | None = None):
        """
        Clears the cache.

        Args:
            prefix: If provided, only keys starting with this prefix will be removed.
        """
        if prefix:
            keys_to_remove = [k for k in self.cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self.cache[k]
        else:
            self.cache.clear()

    def get_channel_metadata(
        self, channel_url: str, force_refresh: bool = False
    ) -> dict:
        """
        Fetches metadata for a YouTube channel.

        Args:
            channel_url: The URL of the channel page.
            force_refresh: If True, bypasses the cache to fetch fresh data.

        Returns:
            A dictionary containing the channel's metadata.
        """
        return self._channel_fetcher.get_channel_metadata(channel_url, force_refresh)

    def get_video_metadata(self, youtube_url: str) -> dict:
        """
        Fetches and parses comprehensive metadata for a given YouTube video.

        Args:
            youtube_url: The full URL of the YouTube video.

        Returns:
            A dictionary containing detailed video metadata.
        """
        return self._video_fetcher.get_video_metadata(youtube_url)

    def get_video_transcript(
        self, video_id: str, languages: List[str] = None
    ) -> List[Dict]:
        """
        Fetches the transcript for a given video.

        Args:
            video_id: The ID of the YouTube video.
            languages: A list of language codes to prioritize (e.g., ['en', 'de']).
                       If None, it will default to English.

        Returns:
            A list of transcript snippets, or an empty list if not found.
        """
        return self._transcript_fetcher.get_transcript(video_id, languages)

    def get_channel_videos(
        self,
        channel_url: str,
        force_refresh: bool = False,
        fetch_full_metadata: bool = False,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        filters: dict | None = None,
        stop_at_video_id: str | None = None,
        max_videos: int = -1,
    ) -> Generator[dict, None, None]:
        """
        Fetches videos from a YouTube channel's "Videos" tab.

        This method handles pagination automatically and provides extensive filtering
        options. It intelligently combines date parameters (`start_date`, `end_date`)
        with any date conditions specified in the `filters` dictionary.

        Args:
            channel_url: The URL of the channel.
            force_refresh: If True, bypasses the cache for the initial page load.
            fetch_full_metadata: If True, performs an additional request for each
                video to get its complete metadata (e.g., likes, category). This is
                required for "slow filters".
            start_date: The earliest publish date for videos to include.
                Can be a `date` object or a string (e.g., "2023-01-01", "3 weeks ago").
            end_date: The latest publish date for videos to include.
            filters: A dictionary of filter conditions to apply.
            stop_at_video_id: If provided, pagination will stop once this video ID
                is found.
            max_videos: The maximum number of videos to return (-1 for all).

        Yields:
            A dictionary for each video that matches the criteria.
        """
        return self._channel_fetcher.get_channel_videos(
            channel_url,
            force_refresh,
            fetch_full_metadata,
            start_date,
            end_date,
            filters,
            stop_at_video_id,
            max_videos,
        )

    def get_playlist_videos(
        self,
        playlist_id: str,
        fetch_full_metadata: bool = False,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        filters: dict | None = None,
        stop_at_video_id: str | None = None,
        max_videos: int = -1,
    ) -> Generator[dict, None, None]:
        """
        Fetches videos from a YouTube playlist.

        Handles pagination and filtering. Note that date filtering for playlists
        is a "slow" operation and will trigger a full metadata fetch for each video.

        Args:
            playlist_id: The ID of the playlist.
            fetch_full_metadata: If True, performs an additional request for each
                video to get its complete metadata. Required for "slow filters".
            start_date: The earliest publish date for videos to include.
            end_date: The latest publish date for videos to include.
            filters: A dictionary of filter conditions to apply.
            stop_at_video_id: If provided, pagination will stop once this video ID
                is found.
            max_videos: The maximum number of videos to return (-1 for all).

        Yields:
            A dictionary for each video that matches the criteria.
        """
        return self._playlist_fetcher.get_playlist_videos(
            playlist_id,
            fetch_full_metadata,
            start_date,
            end_date,
            filters,
            stop_at_video_id,
            max_videos,
        )

    def get_channel_shorts(
        self,
        channel_url: str,
        force_refresh: bool = False,
        fetch_full_metadata: bool = False,
        filters: dict | None = None,
        stop_at_video_id: str | None = None,
        max_videos: int = -1,
    ) -> Generator[dict, None, None]:
        """
        Fetches shorts from a YouTube channel's shorts tab.

        Args:
            channel_url: The URL of the channel's shorts page.
            force_refresh: Whether to bypass the cache and fetch fresh data.
            fetch_full_metadata: Whether to fetch full metadata for each short.
            filters: A dictionary of filter conditions.
            stop_at_video_id: The ID of the short to stop fetching at.
            max_videos: The maximum number of shorts to fetch (-1 for all).

        Returns:
            A generator of short dictionaries.
        """
        return self._channel_fetcher.get_channel_shorts(
            channel_url,
            force_refresh,
            fetch_full_metadata,
            filters,
            stop_at_video_id,
            max_videos,
        )

    def get_video_comments(
        self,
        youtube_url: str,
        limit: int | None = 100,
        sort_by: str = "recent",
        progress_callback: Callable[[int], None] | None = None,
        since_date: date | str | None = None,
        filters: dict | None = None,
    ):
        """
        Get comments for a specific YouTube video.

        Args:
            youtube_url (str): The full URL of the YouTube video.
            limit (int | None, optional): The maximum number of comments to fetch. Defaults to 100. Pass None or -1 for unbounded — but you must also pass `since_date` (safety guard against runaway pagination on popular videos).
            sort_by (str, optional): The order to sort comments by. Can be 'recent' (default — chronological, required for `since_date` short-circuit) or 'top' (YouTube's editorial ranking).
            progress_callback (Callable[[int], None], optional): A function to be called
                with the number of comments fetched so far. Defaults to None.
            since_date (date | str | None, optional): The date from which to fetch comments.
                Can be a date object, a string in the format "YYYY-MM-DD", or None for no filter. The only filter that short-circuits pagination.
            filters (dict | None, optional): Comment-level predicates applied after fetch. Supported keys: text, author, like_count, reply_count, publish_date, is_reply, is_hearted_by_owner, is_by_owner, channel_id. These do NOT reduce request count — they operate on the in-memory comment list. Use `since_date` for request reduction.

        Yields:
            dict: A dictionary representing a single comment.
        """
        resolved_date = self._resolve_date(since_date)
        if (limit is None or limit < 0) and resolved_date is None:
            raise ValueError(
                "Unbounded comment fetching (limit=None or limit<0) requires "
                "since_date to be set, to cap the request count. Pass a "
                "since_date (works with the default sort_by='recent') or use "
                "a finite limit."
            )
        video_id = extract_video_id(youtube_url)
        comments_generator = self._comment_fetcher.get_comments(
            video_id,
            limit=limit,
            sort_by=sort_by,
            progress_callback=progress_callback,
            since_date=resolved_date,
            filters=filters,
        )

        yield from comments_generator

    def get_video_comments_with_reply_tokens(
        self,
        youtube_url: str,
        limit: int | None = 100,
        sort_by: str = "recent",
        progress_callback: Callable[[int], None] | None = None,
        since_date: date | str | None = None,
        filters: dict | None = None,
    ):
        """
        Get comments for a specific YouTube video, including reply continuation tokens.

        Args:
            youtube_url (str): The full URL of the YouTube video.
            limit (int | None, optional): The maximum number of comments to fetch. Defaults to 100. Pass None or -1 for unbounded — but you must also pass `since_date`.
            sort_by (str, optional): The order to sort comments by. Can be 'recent' (default — chronological) or 'top' (YouTube's editorial ranking).
            progress_callback (Callable[[int], None], optional): A function to be called
                with the number of comments fetched so far. Defaults to None.
            since_date (date | str | None, optional): The date from which to fetch comments. Same semantics as get_video_comments.
            filters (dict | None, optional): Same semantics as get_video_comments.

        Yields:
            dict: A dictionary representing a single comment, including 'reply_continuation_token'
                  field for comments that have replies.
        """
        resolved_date = self._resolve_date(since_date)
        if (limit is None or limit < 0) and resolved_date is None:
            raise ValueError(
                "Unbounded comment fetching (limit=None or limit<0) requires "
                "since_date to be set, to cap the request count."
            )
        video_id = extract_video_id(youtube_url)
        comments_generator = self._comment_fetcher.get_comments(
            video_id,
            limit=limit,
            sort_by=sort_by,
            progress_callback=progress_callback,
            since_date=resolved_date,
            include_reply_continuation=True,
            filters=filters,
        )

        yield from comments_generator

    def get_comment_replies(
        self,
        youtube_url: str,
        reply_continuation_token: str,
        limit: int = 100,
        progress_callback: Callable[[int], None] | None = None,
    ):
        """
        Get replies for a specific comment.

        Args:
            youtube_url (str): The full URL of the YouTube video.
            reply_continuation_token (str): The continuation token for the specific reply thread.
            limit (int, optional): The maximum number of replies to fetch. Defaults to 100.
            progress_callback (Callable[[int], None], optional): A function to be called
                with the number of replies fetched so far. Defaults to None.

        Yields:
            dict: A dictionary representing a single reply comment.
        """
        video_id = extract_video_id(youtube_url)
        replies_generator = self._comment_fetcher.get_comment_replies(
            video_id,
            reply_continuation_token=reply_continuation_token,
            limit=limit,
            progress_callback=progress_callback,
        )

        yield from replies_generator

    def _resolve_date(self, d: str | date | None) -> date | None:
        if d is None:
            return None
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        try:
            return parse_relative_date_string(d)
        except ValueError as e:
            raise ValueError(
                f"Invalid date format: {d}. Use 'YYYY-MM-DD' or a relative string like '2 weeks ago'."
            ) from e
