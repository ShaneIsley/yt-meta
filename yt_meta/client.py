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
from .utils import CONSENT_COOKIE, extract_video_id

logger = logging.getLogger(__name__)


class YtMeta:
    """Client for YouTube video, channel, playlist, comment and transcript metadata.

    Use it as a context manager, or call close() when done. Listing and
    comment methods return generators: arguments are checked when the
    method is called, and requests start on first iteration.
    """

    def __init__(
        self,
        cache_path: str | None = None,
        cache: MutableMapping | None = None,
        cache_ttl_seconds: int = 86400,
        accept_cookies: bool = False,
    ):
        """Create a client.

        Args:
            cache_path: Path of a SQLite file for the built-in persistent cache.
            cache: Any MutableMapping to use as the cache, such as a dict or a
                diskcache.Cache. Takes precedence over cache_path. With neither,
                nothing is cached.
            cache_ttl_seconds: Lifetime of built-in SQLite cache entries, in
                seconds. Ignored when cache is given.
            accept_cookies: Set YouTube's consent cookie so requests from regions
                with a cookie-consent page (such as the EU) aren't redirected to
                consent.youtube.com. Off by default because it accepts YouTube's
                cookies on your behalf.
        """
        self.session = Client(headers={"Accept-Language": "en-US,en;q=0.5"})
        if accept_cookies:
            # YouTube's documented consent-bypass cookie. Set on the single
            # shared session, so it covers every fetcher (video / channel /
            # playlist / comment); M1/L2 unified them onto this session.
            self.session.cookies.set(*CONSENT_COOKIE, domain=".youtube.com")
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
        self._transcript_fetcher = TranscriptFetcher(accept_cookies=accept_cookies)

    @property
    def comment_fetcher(self) -> CommentFetcher:
        """The underlying CommentFetcher, for lower-level comment access."""
        return self._comment_fetcher

    def close(self) -> None:
        """Close the HTTP session and the built-in SQLite cache.

        Safe to call more than once. Called automatically on leaving a
        ``with YtMeta() as client:`` block.
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
        """Remove cached entries.

        Args:
            prefix: Remove only keys starting with this prefix, such as
                "video_meta:". None removes everything.
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
        """Fetch a channel's metadata.

        Args:
            channel_url: The channel's home page or any of its tabs.
            force_refresh: Skip the cache.

        Returns:
            title, description, channel_id, vanity_url, keywords and
            is_family_safe. No subscriber or view counts.

        Raises:
            VideoUnavailableError: The request failed.
            MetadataParsingError: The page could not be read.
        """
        return self._channel_fetcher.get_channel_metadata(channel_url, force_refresh)

    @staticmethod
    def _resolve_video_target(
        youtube_url: str | None, video_id: str | None
    ) -> str:
        """M9: video-targeting methods accept either ``youtube_url`` or
        ``video_id`` as a keyword. Exactly one must be provided. Returns
        the raw value (a URL or a bare id); callers run it through
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
        """Fetch a video's metadata and availability status.

        Args:
            youtube_url: The video, as any URL form (watch?v=, youtu.be/,
                /shorts/, /live/) or a bare 11-character id.
            video_id: Alias for youtube_url. Pass exactly one.
            force_refresh: Skip the cache, to re-check availability.

        Returns:
            A dict with title, channel, counts, an exact timezone-aware
            publish_date and more, or None if the page had no player data at
            all. Every dict has status fields:

            - status: "ok", "upcoming" (premiere or live event not started) or
              "unavailable".
            - status_reason: YouTube's reason text when status is not "ok".
            - status_checked_at, status_changed_at: ISO-8601 UTC times of this
              check and of the last status change.

            When a cached video is found unavailable on a later check, the
            cached title and counts are kept and only the status fields change.

        Raises:
            VideoUnavailableError: The request failed. An unavailable video is
                reported through status, not raised.
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
        """Fetch a video's transcript.

        Args:
            video_id: The video, as a bare id or any URL form.
            languages: Language codes in order of preference. Defaults to ["en"].
            youtube_url: Alias for video_id. Pass exactly one.

        Returns:
            {text, start, duration} snippets in the first available language,
            or [] if the video has no transcript in those languages.

        Raises:
            Errors from youtube_transcript_api other than "no transcript", such
            as rate limiting or network failures.
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
        """Yield the channel's Videos tab, newest first.

        start_date and end_date are combined with any publish_date condition in
        filters; on its side, each replaces that condition's bound. Pagination
        stops once the listing passes start_date.

        Args:
            channel_url: The channel's home page or any of its tabs.
            force_refresh: Skip the cache for the listing pages.
            fetch_full_metadata: Fetch each item's own page for the full fields
                and an exact date, one request per item. Turned on automatically
                by slow filters.
            filters: Field conditions; see the README's Filtering section.
            stop_at_video_id: Stop after this video, whether or not it passes
                the filters. It is yielded if it does.
            max_videos: Stop after this many results; -1 for no limit.
            start_date: Earliest publish date: a date, "YYYY-MM-DD" or a relative
                string such as "3 weeks ago".
            end_date: Latest publish date, in the same forms.

        Yields:
            A dict for each matching video.

        Raises:
            ValueError, TypeError: On call, for a non-YouTube URL or bad filters.
            VideoUnavailableError: During iteration, if a page request fails.
            MetadataParsingError: During iteration, if a page can't be read.
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
        """Yield the channel's videos newer than since_video_id, newest first.

        The marker itself is not yielded, and pagination stops at it, so the
        cost is proportional to the number of new videos. Save the first
        yielded id for the next run.

        Args:
            channel_url: The channel URL.
            since_video_id: Newest video id seen on the previous run. None yields
                from the newest video; bound it with max_videos. A marker that no
                longer exists also yields everything.
            fetch_full_metadata: Fetch each new video's full metadata.
            force_refresh: Skip the cache for the listing pages.
            max_videos: Cap on yielded videos; -1 for no cap.

        Yields:
            A dict for each video newer than the marker.
        """
        videos = self._channel_fetcher.get_channel_videos(
            channel_url,
            force_refresh=force_refresh,
            fetch_full_metadata=fetch_full_metadata,
            stop_at_video_id=since_video_id,
            max_videos=max_videos,
        )
        return self._until_marker(videos, since_video_id)

    @staticmethod
    def _until_marker(videos, since_video_id):
        for video in videos:
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
        """Yield the channel's videos published in a window, with exact dates.

        A plain date filter with fetch_full_metadata=True fetches every video
        near the window. This binary-searches the listing instead, at about
        2*log2(n) full-metadata requests, and fetches only the videos inside.

        Args:
            channel_url: The channel URL.
            start_date: Window start, required: a string, date or datetime.
                datetime bounds give an hour-level window; a bound without a
                timezone is compared with the video's local wall-clock time.
            end_date: Window end; None means up to the newest video.
            force_refresh: Skip the cache for the listing pages.

        Yields:
            Full-metadata dicts with publish_date_precision "exact", newest
            first.

        Raises:
            ValueError: On call, if start_date is missing or the URL is invalid.
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
        """Yield a playlist's videos in playlist order.

        Date filters compare the listing's approximate dates, so they cost no
        extra requests, but scan the whole playlist (it may not be in date
        order). An item with no listing date is dropped unless
        fetch_full_metadata=True, in which case its exact date is checked.

        Args:
            playlist_id: The playlist id (the list= URL parameter).
            fetch_full_metadata: Fetch each video's own page for the full fields
                and an exact date, one request per video. Turned on
                automatically by slow filters.
            start_date: Earliest publish date: a date, "YYYY-MM-DD" or relative
                string.
            end_date: Latest publish date, in the same forms.
            filters: Field conditions; see the README's Filtering section.
            stop_at_video_id: Stop after this video, whether or not it passes
                the filters. It is yielded if it does.
            max_videos: Stop after this many results; -1 for no limit.

        Yields:
            A dict for each matching video.
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

    def get_playlist_metadata(self, playlist_id: str) -> dict:
        """Fetch a playlist's own metadata, not its videos.

        Args:
            playlist_id: The playlist id (the list= URL parameter).

        Returns:
            title, author, description, video_count and playlist_id.
        """
        return self._playlist_fetcher.get_playlist_metadata(playlist_id)

    def get_channel_shorts(
        self,
        channel_url: str,
        force_refresh: bool = False,
        fetch_full_metadata: bool = False,
        filters: dict | None = None,
        stop_at_video_id: str | None = None,
        max_videos: int = -1,
    ) -> Generator[dict, None, None]:
        """Yield the channel's Shorts tab.

        The listing has only title and view_count; everything else, including
        publish_date, needs fetch_full_metadata=True.

        Args:
            channel_url: The channel's home page or any of its tabs.
            force_refresh: Skip the cache for the listing pages.
            fetch_full_metadata: Fetch each item's own page for the full fields
                and an exact date, one request per item. Turned on automatically
                by slow filters.
            filters: Field conditions; see the README's Filtering section.
            stop_at_video_id: Stop after this video, whether or not it passes
                the filters. It is yielded if it does.
            max_videos: Stop after this many results; -1 for no limit.

        Yields:
            A dict for each matching Short.
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
        """Yield the channel's Live tab: live, upcoming and past streams.

        The Videos tab does not include these. Items are shaped like channel
        videos, plus is_upcoming and scheduled_text (the listing's "Scheduled
        for ..." text). fetch_full_metadata=True adds the exact
        scheduled_start_time and status.

        Args:
            channel_url: The channel's home page or any of its tabs.
            force_refresh: Skip the cache for the listing pages.
            fetch_full_metadata: Fetch each item's own page for the full fields
                and an exact date, one request per item. Turned on automatically
                by slow filters.
            filters: Field conditions; see the README's Filtering section.
            stop_at_video_id: Stop after this video, whether or not it passes
                the filters. It is yielded if it does.
            max_videos: Stop after this many results; -1 for no limit.

        Yields:
            A dict for each matching stream.
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
        """Yield a video's top-level comments.

        Args:
            youtube_url: The video, as any URL form or a bare id.
            limit: Maximum comments. None or -1 for no limit, which requires
                since_date.
            sort_by: "recent" (newest first) or "top" (YouTube's ranking).
            progress_callback: Called with the running count after each comment.
            since_date: Only comments on or after this date (date, datetime,
                "YYYY-MM-DD" or a relative string such as "2 weeks ago").
                Requires sort_by="recent"; fetching stops at the first older
                comment.
            filters: Comment field conditions, applied to fetched comments.
            video_id: Alias for youtube_url. Pass exactly one.

        Yields:
            A dict for each comment. Comment dates are always approximate.

        Raises:
            ValueError: On call, for an unknown sort_by, since_date with
                sort_by="top", limit=None without since_date, or bad filters.
            VideoUnavailableError: During iteration, if a request fails.
            MetadataParsingError: During iteration, if the page has no API key,
                or since_date is set and YouTube offers no newest-first order.
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
        return self._comment_fetcher.get_comments(
            resolved_id,
            limit=limit,
            sort_by=sort_by,
            progress_callback=progress_callback,
            since_date=resolved_date,
            filters=filters,
        )

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
        """Yield top-level comments with reply tokens.

        As get_video_comments, and each comment that has replies also carries a
        reply_continuation_token to pass to get_comment_replies.

        Args:
            youtube_url: The video, as any URL form or a bare id.
            limit: Maximum comments. None or -1 for no limit, which requires
                since_date.
            sort_by: "recent" (newest first) or "top" (YouTube's ranking).
            progress_callback: Called with the running count after each comment.
            since_date: Only comments on or after this date (date, datetime,
                "YYYY-MM-DD" or a relative string such as "2 weeks ago").
                Requires sort_by="recent"; fetching stops at the first older
                comment.
            filters: Comment field conditions, applied to fetched comments.
            video_id: Alias for youtube_url. Pass exactly one.

        Yields:
            A dict for each comment.

        Raises:
            ValueError: On call, for an unknown sort_by, since_date with
                sort_by="top", limit=None without since_date, or bad filters.
            VideoUnavailableError: During iteration, if a request fails.
            MetadataParsingError: During iteration, if the page has no API key,
                or since_date is set and YouTube offers no newest-first order.
        """
        youtube_url = self._resolve_video_target(youtube_url, video_id)
        resolved_date = self._resolve_date(since_date)
        if (limit is None or limit < 0) and resolved_date is None:
            raise ValueError(
                "Unbounded comment fetching (limit=None or limit<0) requires "
                "since_date to be set, to cap the request count."
            )
        resolved_id = extract_video_id(youtube_url)
        return self._comment_fetcher.get_comments(
            resolved_id,
            limit=limit,
            sort_by=sort_by,
            progress_callback=progress_callback,
            since_date=resolved_date,
            include_reply_continuation=True,
            filters=filters,
        )

    def get_comment_replies(
        self,
        youtube_url: str | None = None,
        reply_continuation_token: str | None = None,
        limit: int = 100,
        progress_callback: Callable[[int], None] | None = None,
        *,
        video_id: str | None = None,
    ):
        """Yield the replies in one comment thread.

        Args:
            youtube_url: The video, as any URL form or a bare id.
            reply_continuation_token: The thread's token, from
                get_video_comments_with_reply_tokens.
            limit: Maximum replies; None or -1 for no limit.
            progress_callback: Called with the running count after each reply.
            video_id: Alias for youtube_url. Pass exactly one.

        Yields:
            A dict for each reply.
        """
        youtube_url = self._resolve_video_target(youtube_url, video_id)
        resolved_id = extract_video_id(youtube_url)
        return self._comment_fetcher.get_comment_replies(
            resolved_id,
            reply_continuation_token=reply_continuation_token,
            limit=limit,
            progress_callback=progress_callback,
        )

    def get_comment_threads(
        self,
        youtube_url: str | None = None,
        *,
        video_id: str | None = None,
        limit: int | None = 20,
        replies_per_thread: int = 10,
        sort_by: str = "recent",
        since_date: date | str | None = None,
        filters: dict | None = None,
    ):
        """Yield (comment, replies) pairs for a video.

        Costs one request per page of about 20 top-level comments, plus one per
        page of about 10 replies for each comment that has replies. YouTube's
        reply_count can exceed the replies it serves (held or removed replies),
        so treat it as an upper bound.

        Args:
            youtube_url: The video, as any URL form or a bare id.
            video_id: Alias for youtube_url. Pass exactly one.
            limit: Maximum top-level comments; as for get_video_comments.
            replies_per_thread: Maximum replies per thread; 0 skips reply
                requests.
            sort_by: "recent" (newest first, the default for every comment
                method) or "top" (YouTube's ranking, where threads with replies
                tend to come first).
            since_date: As for get_video_comments.
            filters: Comment field conditions, applied to top-level comments.

        Yields:
            (comment, replies) tuples; replies is [] for a comment without any.
        """
        target = self._resolve_video_target(youtube_url, video_id)
        comments = self.get_video_comments_with_reply_tokens(
            video_id=target,
            limit=limit,
            sort_by=sort_by,
            since_date=since_date,
            filters=filters,
        )
        return self._iter_threads(target, comments, replies_per_thread)

    def _iter_threads(self, target, comments, replies_per_thread):
        for comment in comments:
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
