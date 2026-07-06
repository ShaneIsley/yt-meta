# yt_meta/client.py

import logging
from collections.abc import Callable, Generator, MutableMapping
from datetime import date, datetime

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
        accept_cookies: bool = False,
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
            accept_cookies: Opt in to bypassing YouTube's EU cookie-consent
                   wall. When ``True``, a ``SOCS`` consent cookie is set on
                   the session so YouTube serves content directly instead of
                   a 302 redirect to consent.youtube.com. Default ``False``
                   — no consent cookie is set, behavior is unchanged. Set
                   this to ``True`` if you see a ``302`` redirect to
                   ``consent.youtube.com`` (region-gated, e.g. the EU). This
                   is a conscious choice to accept YouTube's cookies on your
                   behalf, hence the explicit opt-in.
        """
        self.session = Client(headers={"Accept-Language": "en-US,en;q=0.5"})
        if accept_cookies:
            # YouTube's documented consent-bypass cookie. Set on the single
            # shared session, so it covers every fetcher (video / channel /
            # playlist / comment) — M1/L2 unified them onto this session.
            self.session.cookies.set(
                "SOCS",
                "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg",
                domain=".youtube.com",
            )
            logger.info("accept_cookies=True: set SOCS consent cookie on session.")
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

    @staticmethod
    def _resolve_video_target(
        youtube_url: str | None, video_id: str | None
    ) -> str:
        """M9: video-targeting methods accept either ``youtube_url`` or
        ``video_id`` as a keyword. Exactly one must be provided. Returns
        the raw value (a URL or a bare id) — callers run it through
        ``extract_video_id`` as needed.
        """
        provided = [v for v in (youtube_url, video_id) if v is not None]
        if len(provided) != 1:
            raise ValueError(
                "Provide exactly one of youtube_url or video_id "
                f"(got youtube_url={youtube_url!r}, video_id={video_id!r})"
            )
        return provided[0]

    def get_video_metadata(
        self,
        youtube_url: str | None = None,
        *,
        video_id: str | None = None,
        force_refresh: bool = False,
    ) -> dict | None:
        """
        Fetches and parses comprehensive metadata for a given YouTube video.

        Args:
            youtube_url: The video URL (or a bare 11-char id).
            video_id: Alias — pass the id (or a URL) by this keyword
                instead. Exactly one of youtube_url / video_id is
                required.
            force_refresh: Re-fetch even on a cache hit, to pick up
                availability/status changes.

        Returns:
            A dictionary of metadata (including ``status`` /
            ``status_reason`` / ``status_checked_at`` /
            ``status_changed_at`` fields), or ``None`` if the page
            yielded no player response at all. See get_video_metadata on
            VideoFetcher for the full status contract.
        """
        target = self._resolve_video_target(youtube_url, video_id)
        return self._video_fetcher.get_video_metadata(
            target, force_refresh=force_refresh
        )

    def get_video_transcript(
        self,
        video_id: str | None = None,
        languages: list[str] = None,
        *,
        youtube_url: str | None = None,
    ) -> list[dict]:
        """
        Fetches the transcript for a given video.

        Args:
            video_id: The video id (or a full URL — M9 routes it through
                extract_video_id, so URLs and youtu.be links work too).
            languages: A list of language codes to prioritize (e.g.,
                ['en', 'de']). If None, defaults to English.
            youtube_url: Alias for ``video_id``. Exactly one of the two
                is required.

        Returns:
            A list of transcript snippets, or an empty list if not found.
        """
        target = self._resolve_video_target(youtube_url, video_id)
        return self._transcript_fetcher.get_transcript(
            extract_video_id(target), languages
        )

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

    def iter_new_videos(
        self,
        channel_url: str,
        since_video_id: str | None = None,
        fetch_full_metadata: bool = False,
        force_refresh: bool = False,
        max_videos: int = -1,
    ):
        """
        Incremental sync: yield a channel's videos newest-first, stopping
        BEFORE ``since_video_id`` — i.e. only what's new since you last
        looked. The first yielded video's id is your new high-water mark.

        Unlike ``get_channel_videos(stop_at_video_id=...)``, the marker
        video itself is NOT yielded (you've already seen it). Pagination
        still stops at the marker, so request cost is proportional to
        how much is new, not to channel size.

        Args:
            channel_url: The channel URL.
            since_video_id: The last video id seen on a previous run.
                ``None`` yields from the newest video onward — bound it
                with ``max_videos`` (a deleted/never-found marker also
                falls back to streaming the whole channel).
            fetch_full_metadata: Fetch full metadata for each new video.
            force_refresh: Bypass the cache for the listing pages.
            max_videos: Safety cap on yielded videos (-1 for no cap).

        Yields:
            A dictionary for each video newer than the marker.
        """
        for video in self._channel_fetcher.get_channel_videos(
            channel_url,
            force_refresh=force_refresh,
            fetch_full_metadata=fetch_full_metadata,
            stop_at_video_id=since_video_id,
            max_videos=max_videos,
        ):
            if since_video_id is not None and video["video_id"] == since_video_id:
                return
            yield video

    def get_videos_published_between(
        self,
        channel_url: str,
        start_date: "str | date | datetime | None" = None,
        end_date: "str | date | datetime | None" = None,
        force_refresh: bool = False,
    ):
        """
        Videos published in an exact window, found with O(log n)
        hydrations — the efficient path for old / narrow date targets.

        Listing dates are approximate (rounded relative text), so a
        plain date filter must hydrate every video in the padded window
        (~365 requests for a ±6-month pad on a daily channel). This
        helper exploits the listing's chronological order instead: it
        binary-searches the window's boundaries with probe hydrations
        (~2·log₂ n), then hydrates only the videos inside.

        Bounds may be ``datetime`` for hour-level windows — membership
        is decided on EXACT (hydrated) dates, naive bounds matching
        wall-clock. Every yielded video is full-metadata with
        ``publish_date_precision == "exact"``.

        Args:
            channel_url: The channel URL.
            start_date: Window start (required) — str/date/datetime.
            end_date: Window end (None = up to the newest video).
            force_refresh: Bypass the cache for the listing pages.

        Yields:
            Full-metadata video dictionaries, newest first.
        """
        return self._channel_fetcher.get_videos_published_between(
            channel_url,
            start_date=start_date,
            end_date=end_date,
            force_refresh=force_refresh,
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

    def get_channel_streams(
        self,
        channel_url: str,
        force_refresh: bool = False,
        fetch_full_metadata: bool = False,
        filters: dict | None = None,
        stop_at_video_id: str | None = None,
        max_videos: int = -1,
    ) -> Generator[dict, None, None]:
        """
        Fetches live streams from a channel's Live (``/streams``) tab —
        live, upcoming/scheduled, and past live content that the Videos
        tab does not include.

        Items use the same shape as ``get_channel_videos``. Upcoming
        streams carry ``is_upcoming=True`` and ``scheduled_text``; pass
        ``fetch_full_metadata=True`` for the precise
        ``scheduled_start_time`` and ``status`` per stream.

        Args:
            channel_url: The channel URL (``/streams`` is appended if absent).
            force_refresh: Whether to bypass the cache and fetch fresh data.
            fetch_full_metadata: Whether to fetch full metadata per stream.
            filters: A dictionary of filter conditions.
            stop_at_video_id: The ID of the stream to stop fetching at.
            max_videos: The maximum number of streams to fetch (-1 for all).

        Returns:
            A generator of stream dictionaries.
        """
        return self._channel_fetcher.get_channel_streams(
            channel_url,
            force_refresh,
            fetch_full_metadata,
            filters,
            stop_at_video_id,
            max_videos,
        )

    def get_video_comments(
        self,
        youtube_url: str | None = None,
        limit: int | None = 100,
        sort_by: str = "recent",
        progress_callback: Callable[[int], None] | None = None,
        since_date: date | str | None = None,
        filters: dict | None = None,
        *,
        video_id: str | None = None,
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
            filters (dict | None, optional): Comment-level predicates applied after fetch. Supported keys: text, author, author_channel_id, like_count, reply_count, publish_date, is_reply, is_hearted, is_creator, is_pinned. These do NOT reduce request count — they operate on the in-memory comment list. Use `since_date` for request reduction.

        Yields:
            dict: A dictionary representing a single comment.
        """
        youtube_url = self._resolve_video_target(youtube_url, video_id)
        resolved_date = self._resolve_date(since_date)
        if (limit is None or limit < 0) and resolved_date is None:
            raise ValueError(
                "Unbounded comment fetching (limit=None or limit<0) requires "
                "since_date to be set, to cap the request count. Pass a "
                "since_date (works with the default sort_by='recent') or use "
                "a finite limit."
            )
        resolved_id = extract_video_id(youtube_url)
        comments_generator = self._comment_fetcher.get_comments(
            resolved_id,
            limit=limit,
            sort_by=sort_by,
            progress_callback=progress_callback,
            since_date=resolved_date,
            filters=filters,
        )

        yield from comments_generator

    def get_video_comments_with_reply_tokens(
        self,
        youtube_url: str | None = None,
        limit: int | None = 100,
        sort_by: str = "recent",
        progress_callback: Callable[[int], None] | None = None,
        since_date: date | str | None = None,
        filters: dict | None = None,
        *,
        video_id: str | None = None,
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
        youtube_url = self._resolve_video_target(youtube_url, video_id)
        resolved_date = self._resolve_date(since_date)
        if (limit is None or limit < 0) and resolved_date is None:
            raise ValueError(
                "Unbounded comment fetching (limit=None or limit<0) requires "
                "since_date to be set, to cap the request count."
            )
        resolved_id = extract_video_id(youtube_url)
        comments_generator = self._comment_fetcher.get_comments(
            resolved_id,
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
        youtube_url: str | None = None,
        reply_continuation_token: str | None = None,
        limit: int = 100,
        progress_callback: Callable[[int], None] | None = None,
        *,
        video_id: str | None = None,
    ):
        """
        Get replies for a specific comment.

        Args:
            youtube_url (str): The video URL (or a bare id). Alias:
                ``video_id=``. Exactly one is required.
            reply_continuation_token (str): The continuation token for the specific reply thread.
            limit (int, optional): The maximum number of replies to fetch. Defaults to 100.
            progress_callback (Callable[[int], None], optional): A function to be called
                with the number of replies fetched so far. Defaults to None.

        Yields:
            dict: A dictionary representing a single reply comment.
        """
        youtube_url = self._resolve_video_target(youtube_url, video_id)
        resolved_id = extract_video_id(youtube_url)
        replies_generator = self._comment_fetcher.get_comment_replies(
            resolved_id,
            reply_continuation_token=reply_continuation_token,
            limit=limit,
            progress_callback=progress_callback,
        )

        yield from replies_generator

    def get_comment_threads(
        self,
        youtube_url: str | None = None,
        *,
        video_id: str | None = None,
        limit: int | None = 20,
        replies_per_thread: int = 10,
        sort_by: str = "top",
        since_date: date | str | None = None,
        filters: dict | None = None,
    ):
        """
        Yield ``(comment, replies)`` tuples — the comment hierarchy in
        one call, wrapping the reply-token two-step
        (``get_video_comments_with_reply_tokens`` +
        ``get_comment_replies`` per thread).

        Request cost is explicit: one request per ~20 top-level
        comments, plus one request per ~10 replies for each comment
        that has replies. Set ``replies_per_thread=0`` for structure
        only (no reply requests at all).

        Args:
            youtube_url: The video URL. Alias: ``video_id=``.
            limit: Maximum top-level comments (same semantics as
                get_video_comments).
            replies_per_thread: Max replies fetched per thread
                (0 = don't fetch replies).
            sort_by: 'top' (default — YouTube's ranking, best for
                thread exploration) or 'recent'.
            since_date: Same semantics as get_video_comments.
            filters: Applied to top-level comments only.

        Yields:
            Tuples of (comment_dict, list_of_reply_dicts). Comments
            without replies yield an empty list.
        """
        target = self._resolve_video_target(youtube_url, video_id)
        for comment in self.get_video_comments_with_reply_tokens(
            video_id=target,
            limit=limit,
            sort_by=sort_by,
            since_date=since_date,
            filters=filters,
        ):
            token = comment.get("reply_continuation_token")
            replies = []
            if token and replies_per_thread:
                replies = list(
                    self.get_comment_replies(
                        video_id=target,
                        reply_continuation_token=token,
                        limit=replies_per_thread,
                    )
                )
            yield comment, replies

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
