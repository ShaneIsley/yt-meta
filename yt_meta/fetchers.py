"""Fetchers: get pages, follow next-page tokens, run the filter pipeline.

Page layout knowledge (where items and tokens live) is in ``parsing``.
Every listing (channel videos / shorts / streams, playlists) goes through
``_BaseFetcher._fetch_page`` for its first page and ``_paginate`` for the
rest, so the rules below hold for all of them.

Error policy
------------
- The first page of a listing, or a single video/channel/playlist page,
  can't be fetched: ``VideoUnavailableError``. It can be fetched but not
  parsed: ``MetadataParsingError``. An empty listing is not an error; it
  yields nothing.
- A later page fails: the same exceptions, raised mid-iteration. Records
  already yielded stay valid.
- One video's full-metadata fetch fails during a listing: logged, and the
  video is skipped (``_process_videos``) or kept with its listing data
  (``get_videos_published_between``, whose bisect needs every index).
- ``VideoFetcher.get_video_metadata`` returns ``None`` when the watch page
  has no player response at all; an unavailable video is a record with
  ``status="unavailable"``, not an error.
"""

import logging
from collections.abc import MutableMapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from . import parsing
from ._retry import request_with_retries
from .date_utils import approx_date_resolution
from .exceptions import MetadataParsingError, VideoUnavailableError
from .filtering import (
    FAST_VIDEO_FILTERS,
    apply_filters,
    build_date_filter,
    condition_has_time,
    partition_filters,
    passes_padded_date_window,
)
from .utils import extract_video_id, validate_youtube_url
from .validators import validate_filters

if TYPE_CHECKING:
    from .fetchers import VideoFetcher

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string. Indirected through a
    module function so tests can monkeypatch a deterministic clock."""
    return datetime.now(timezone.utc).isoformat()


def _apply_status_tracking(parsed: dict, prior: dict | None) -> dict:
    """Attach status lifecycle fields to a freshly parsed video record,
    relative to the previously cached record (``prior``).

    - ``status_checked_at``: always set to now (we just verified it).
    - ``status_changed_at``: now if the status differs from the prior
      record (or there is no prior — first sighting); otherwise carried
      forward from the prior record.
    - When a video is ``unavailable`` and a prior record exists, the
      prior record's content fields (title, channel, counts, …) are
      preserved and the status fields overlaid — so callers never lose
      data they already had. M-b: this must hold on EVERY unavailable
      check, not just the first ok→unavailable transition — a repeat
      check of an already-unavailable video re-preserves the carried
      content instead of overwriting it with the fresh parse's Nones.
    """
    now = _utcnow_iso()
    status = parsed.get("status", "ok")
    prior_status = prior.get("status") if prior else None

    if status == "unavailable" and prior:
        # Unavailable with history — keep the last-known-good content.
        # Only "unavailable": an "upcoming" parse is complete, and taking
        # the prior record kept a rescheduled premiere's old start time.
        result = dict(prior)
        result["status"] = status
        result["status_reason"] = parsed.get("status_reason")
    else:
        result = dict(parsed)

    result["status_checked_at"] = now
    if prior_status is not None and prior_status == status:
        result["status_changed_at"] = prior.get("status_changed_at", now)
    else:
        result["status_changed_at"] = now
    return result


def _merge_hydrated(video: dict, full_meta: dict) -> dict:
    """Merge a watch-page parse into a listing record.

    An unavailable watch page (members-only, private) parses to
    title=None, view_count=0. It adds status and anything the listing
    lacks, but never replaces real listing values with those blanks,
    which made filters like view_count < 100 match. Otherwise the parse
    wins, and the listing's relative date text is kept (Option A: the
    watch page has none).
    """
    if full_meta.get("status") == "unavailable":
        return {**full_meta, **{k: v for k, v in video.items() if v is not None}}
    merged = {**video, **full_meta}
    if video.get("publish_date_text") and not merged.get("publish_date_text"):
        merged["publish_date_text"] = video["publish_date_text"]
    return merged


def _process_videos(
    video_generator,
    *,
    video_fetcher,
    must_fetch_full_metadata,
    fast_filters,
    slow_filters,
    stop_at_video_id,
    max_videos,
    log,
    coarse_date_cond=None,
):
    """The per-video filter+enrich loop, extracted as a free function so
    it can be unit-tested without a fetcher instance (L5). Applies fast
    filters on the raw renderer dict, optionally fetches full metadata
    and merges it, applies slow filters on the merged dict, and yields
    survivors until stop_at_video_id or max_videos."""

    def admit(video):
        """The merged video if it passes every filter, else None."""
        # Date-funnel coarse cut (see _run_filtered_pipeline): padded
        # pre-hydration screen on the approximate date. Skips the
        # hydration request for videos safely outside the window.
        if coarse_date_cond is not None and not passes_padded_date_window(
            video, coarse_date_cond
        ):
            return None
        # M-e: when full metadata will be fetched anyway, a fast-filter
        # field that is missing/None on the raw item is DEFERRED to the
        # merged dict instead of dropping the video one request too
        # early (e.g. a page shape without date text + a publish_date
        # filter + fetch_full_metadata=True). Without hydration the
        # documented M6 missing-field semantics apply unchanged.
        if must_fetch_full_metadata:
            deferred_filters = {
                k: v for k, v in fast_filters.items() if video.get(k) is None
            }
            immediate_filters = {
                k: v for k, v in fast_filters.items() if k not in deferred_filters
            }
        else:
            deferred_filters, immediate_filters = {}, fast_filters
        if not apply_filters(video, immediate_filters):
            return None
        merged_video = video
        if must_fetch_full_metadata:
            try:
                video_url = f"https://www.youtube.com/watch?v={video['video_id']}"
                full_meta = video_fetcher.get_video_metadata(video_url)
                if full_meta:
                    merged_video = _merge_hydrated(video, full_meta)
                elif slow_filters:
                    return None
            except (VideoUnavailableError, MetadataParsingError) as e:
                log.error(
                    "Error fetching metadata for video_id %s: %s",
                    video["video_id"],
                    e,
                )
                return None
        if not apply_filters(merged_video, {**slow_filters, **deferred_filters}):
            return None
        return merged_video

    videos_processed = 0
    for video in video_generator:
        merged_video = admit(video)
        if merged_video is not None:
            yield merged_video
            videos_processed += 1
        # The marker ends pagination whether or not it passed the
        # filters (or its metadata fetch failed) — checking only after
        # a yield walked the whole channel when the marker was filtered.
        if stop_at_video_id and video["video_id"] == stop_at_video_id:
            return
        if max_videos != -1 and videos_processed >= max_videos:
            return


def _run_filtered_pipeline(
    raw_generator,
    *,
    filters,
    content_type,
    fetch_full_metadata,
    video_fetcher,
    logger,
    stop_at_video_id,
    max_videos,
):
    """The shared filter-pipeline epilogue, extracted from the three
    fetcher entrypoints (get_channel_videos / get_channel_shorts /
    get_playlist_videos) which previously hand-copied it (L5).

    Partitions filters into fast/slow, decides whether full metadata
    must be fetched (always when a slow filter is present), logs the
    auto-enable, then yields from the per-video loop. Independently
    unit-testable — no HTTP, no fetcher instance required.
    """
    fast_filters, slow_filters = partition_filters(
        filters or {}, content_type=content_type
    )
    must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)
    if slow_filters and not fetch_full_metadata:
        logger.warning(
            "Slow filters %s provided without fetch_full_metadata=True. "
            "Full metadata will be fetched.",
            list(slow_filters.keys()),
        )

    # The date funnel: when hydrating, publish_date bounds are decided
    # by the EXACT (post-merge) date; pre-merge, the approximate date
    # only serves as a coarse cut padded by its own rounding error
    # (passes_padded_date_window), so near-boundary videos survive to
    # hydration. Without hydration, approximate dates are all there is
    # — date-granularity bounds work as documented, but hour-level
    # bounds cannot be honored and must fail loudly rather than compare
    # against query-time noise.
    coarse_date_cond = None
    pd_cond = fast_filters.get("publish_date")
    if must_fetch_full_metadata and pd_cond is not None:
        coarse_date_cond = pd_cond
        fast_filters = {k: v for k, v in fast_filters.items() if k != "publish_date"}
        slow_filters = {**slow_filters, "publish_date": pd_cond}
    elif condition_has_time(pd_cond):
        raise ValueError(
            "publish_date bounds with time-of-day require "
            "fetch_full_metadata=True — listing dates are approximate "
            "(parsed from relative text) and carry no meaningful time."
        )

    return _process_videos(
        raw_generator,
        video_fetcher=video_fetcher,
        must_fetch_full_metadata=must_fetch_full_metadata,
        fast_filters=fast_filters,
        slow_filters=slow_filters,
        coarse_date_cond=coarse_date_cond,
        stop_at_video_id=stop_at_video_id,
        max_videos=max_videos,
        log=logger,
    )


class _BaseFetcher:
    """Minimal shared base for ChannelFetcher and PlaylistFetcher.

    Holds the common construction (session / cache / video_fetcher /
    logger) and the continuation-fetch HTTP method they both use. The
    filter-pipeline logic that used to live here is now the free
    functions ``_run_filtered_pipeline`` / ``_process_videos`` above —
    extracted per L5 so it's unit-testable in isolation. What remains
    here is genuinely shared behavior, not a pipeline shim.
    """

    def __init__(
        self,
        session: httpx.Client,
        cache: MutableMapping | None,
        video_fetcher: "VideoFetcher",
    ):
        self.session = session
        self.cache = cache
        self.video_fetcher = video_fetcher
        self.logger = logger

    def _get_continuation_data(self, token: str, ytcfg: dict):
        cache_key = f"continuation:{token}"
        if cache_key in self.cache:
            self.logger.info(f"Cache hit for continuation token: {token[:10]}...")
            return self.cache[cache_key]
        # Mid-pagination failures surface as the library's own errors,
        # not raw KeyError / httpx / JSONDecodeError.
        try:
            data = {"context": ytcfg["INNERTUBE_CONTEXT"], "continuation": token}
            api_key = ytcfg["INNERTUBE_API_KEY"]
        except KeyError as e:
            raise MetadataParsingError(
                f"Page config is missing {e} needed to request the next page"
            ) from e
        url = f"https://www.youtube.com/youtubei/v1/browse?key={api_key}"
        try:
            # H9: the continuation/browse POST is the tight pagination loop
            # most likely to be rate-limited; wrap it in retry/backoff.
            response = request_with_retries(
                lambda: self.session.post(url, json=data, timeout=10)
            )
        except httpx.HTTPError as e:
            raise VideoUnavailableError(f"Could not fetch the next page: {e}") from e
        try:
            result = response.json()
        except ValueError as e:
            raise MetadataParsingError(
                f"Next-page response was not valid JSON: {e}"
            ) from e
        self.cache[cache_key] = result
        return result

    def _fetch_page(
        self,
        url: str,
        *,
        what: str,
        cache_key: str | None = None,
        force_refresh: bool = False,
        require_ytcfg: bool = True,
        **context,
    ) -> tuple[dict, dict | None]:
        """GET a browse page (channel tab, playlist) and return
        ``(initial_data, ytcfg)``, cached under ``cache_key`` when given.

        ``what`` names the page in error messages; ``context`` (e.g.
        ``channel_url=`` or ``playlist_id=``) is attached to the error.
        Raises per the module's error policy. Raw HTML is never cached
        (M11): only the two parsed blobs are used downstream.
        """
        if cache_key and not force_refresh and cache_key in self.cache:
            self.logger.info("Using cached %s: %s", what, cache_key)
            return self.cache[cache_key]
        try:
            self.logger.info("Fetching %s: %s", what, url)
            response = request_with_retries(
                lambda: self.session.get(url, timeout=10)
            )
            html = response.text
        except httpx.HTTPError as e:
            raise VideoUnavailableError(
                f"Could not fetch {what}: {e}", **context
            ) from e
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        if not initial_data:
            raise MetadataParsingError(
                f"Could not extract ytInitialData from {what}.", **context
            )
        ytcfg = parsing.find_ytcfg(html)
        if require_ytcfg and not ytcfg:
            raise MetadataParsingError(
                f"Could not extract ytcfg from {what}.", **context
            )
        result = (initial_data, ytcfg)
        if cache_key:
            self.cache[cache_key] = result
        return result

    def _paginate(self, items, ytcfg, parse_page, stop_after=None):
        """Yield records from a listing, following next-page tokens.

        ``parse_page(items) -> (records, next_token)`` knows the layout
        (see parsing); this only fetches. ``stop_after(records)`` returning
        True ends pagination after the current page has been yielded
        (the date early-stop).
        """
        while True:
            records, token = parse_page(items)
            yield from records
            if not token or (stop_after is not None and stop_after(records)):
                return
            items = parsing.continuation_items(
                self._get_continuation_data(token, ytcfg)
            )


class VideoFetcher:
    """Fetches data related to a single YouTube video."""

    def __init__(self, session: httpx.Client, cache: MutableMapping | None):
        self.session = session
        self.cache = cache

    def get_video_metadata(
        self, youtube_url: str, force_refresh: bool = False
    ) -> dict | None:
        """
        Fetches and parses comprehensive metadata for a given YouTube video.

        Args:
            youtube_url: Any supported form (``watch?v=ID``, ``/shorts/ID``,
                ``youtu.be/ID``, or a bare 11-char ID).
            force_refresh: Re-fetch even on a cache hit. Use this to
                re-check a video's availability and pick up status
                changes (e.g. a video that became unavailable since it
                was last cached).

        Returns:
            A dictionary of metadata, OR ``None`` if the watch page was
            fetched but no player response could be extracted at all
            (a genuinely unparseable page). Every returned dict carries
            video-status lifecycle fields:

              - ``status``: ``"ok"`` or ``"unavailable"``.
              - ``status_reason``: YouTube's reason text when unavailable
                (e.g. "Video unavailable"), else ``None``.
              - ``status_checked_at`` / ``status_changed_at``: ISO-8601
                UTC timestamps of the last check and the last status
                change.

            When a previously-``ok`` video is found ``unavailable``, the
            result PRESERVES the last-known-good content fields and
            overlays the status fields — so prior data is never lost.

        Raises:
            VideoUnavailableError: if the HTTP fetch itself failed
                (network error, 404, rate-limit) — distinct from a
                parsed-but-unavailable video, which is reported via the
                ``status`` field rather than an exception.
        """
        logger.info(f"Fetching video page: {youtube_url}")
        video_id = extract_video_id(youtube_url)
        cache_key = f"video_meta:{video_id}"
        prior = self.cache[cache_key] if cache_key in self.cache else None
        if prior is not None and not force_refresh:
            logger.info(f"Cache hit for video metadata: {video_id}")
            return prior

        # Build a canonical watch URL from the resolved id. Previously the
        # raw input was fetched, which broke for bare-id / youtu.be inputs
        # (the id resolved for the cache key but the GET used the raw
        # string).
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            # C3: this GET runs once per video during full-metadata
            # hydration — the library's highest-volume request — so a
            # transient 429/5xx here must be retried, not kill the
            # calling generator.
            response = request_with_retries(
                lambda: self.session.get(watch_url, timeout=10)
            )
            html = response.text
        except httpx.HTTPError as e:
            # C2: httpx.HTTPError covers BOTH RequestError (connection/
            # timeout) and HTTPStatusError (raise_for_status on 4xx/5xx).
            # Catching only RequestError let status errors escape
            # unwrapped, contradicting the docstring's promise.
            logger.error(f"Failed to fetch video page {watch_url}: {e}")
            raise VideoUnavailableError(
                f"Failed to fetch video page: {e}", video_id=video_id
            ) from e

        player_response_data = parsing.extract_and_parse_json(
            html, "ytInitialPlayerResponse"
        )
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")

        # Only a missing player response is truly unparseable. An
        # unavailable video DOES return a player response (with a
        # non-OK playabilityStatus) — that is reported via `status`,
        # not by returning None.
        if not player_response_data:
            logger.warning(
                f"Could not extract player response for video {video_id}. "
                "The page structure may have changed. Skipping."
            )
            return None

        parsed = parsing.parse_video_metadata(player_response_data, initial_data or {})
        result = _apply_status_tracking(parsed, prior)
        self.cache[cache_key] = result
        return result


class ChannelFetcher(_BaseFetcher):
    """Fetches data related to a YouTube channel's videos and shorts."""

    def __init__(
        self,
        session: httpx.Client,
        cache: MutableMapping | None,
        video_fetcher: VideoFetcher,
    ):
        super().__init__(session, cache, video_fetcher)

    # Channel tab -> cache-key prefix. The prefixes predate the shared
    # page fetch; kept so existing persistent caches stay valid.
    _TAB_CACHE_PREFIX = {
        "videos": "channel_page",
        "shorts": "channel_shorts_page",
        "streams": "channel_streams_page",
    }

    @staticmethod
    def _tab_url(channel_url: str, tab: str) -> str:
        """The channel's ``tab`` URL. Strip first: a trailing slash
        ("…/videos/") used to defeat the suffix check and produce
        "…/videos/videos", which YouTube serves but which split the cache
        key from the plain form."""
        url = channel_url.rstrip("/")
        return url if url.endswith(f"/{tab}") else f"{url}/{tab}"

    def _tab_cache_key(self, channel_url: str, tab: str) -> str:
        return f"{self._TAB_CACHE_PREFIX[tab]}:{self._tab_url(channel_url, tab)}"

    def _get_tab_page_data(
        self, channel_url: str, tab: str, force_refresh: bool = False
    ) -> tuple[dict, dict]:
        validate_youtube_url(channel_url)
        url = self._tab_url(channel_url, tab)
        return self._fetch_page(
            url,
            what=f"channel {tab} page",
            cache_key=self._tab_cache_key(channel_url, tab),
            force_refresh=force_refresh,
            channel_url=url,
        )

    def _get_channel_page_data(
        self, channel_url: str, force_refresh: bool = False
    ) -> tuple[dict, dict]:
        """The channel's Videos tab page, which also carries the channel
        metadata."""
        return self._get_tab_page_data(channel_url, "videos", force_refresh)

    def get_channel_metadata(
        self, channel_url: str, force_refresh: bool = False
    ) -> dict:
        initial_data, _ = self._get_channel_page_data(
            channel_url, force_refresh=force_refresh
        )
        return parsing.parse_channel_metadata(initial_data)

    def _get_raw_tab_generator(
        self, channel_url, tab, force_refresh=False, stop_after=None
    ):
        """Yield raw listing records from a channel tab, every page.

        Videos and Live (streams) share the lockup grid; Shorts has its
        own item shape and is found by title rather than selection.
        """
        if tab == "shorts":
            initial_data, ytcfg = self._get_tab_page_data(
                channel_url, tab, force_refresh
            )
            tab_renderer = parsing.find_channel_tab(initial_data, title="Shorts")
            parse_page = parsing.extract_shorts_from_renderers
        else:
            initial_data, ytcfg = self._get_tab_page_data(
                channel_url, tab, force_refresh
            )
            tab_renderer = parsing.find_channel_tab(initial_data)
            parse_page = parsing.parse_grid_page
        if not tab_renderer:
            raise MetadataParsingError(
                f"Could not find the {tab} tab on the channel page.",
                channel_url=self._tab_url(channel_url, tab),
            )
        yield from self._paginate(
            parsing.tab_grid_items(tab_renderer), ytcfg, parse_page, stop_after
        )

    def _get_raw_channel_videos_generator(
        self, channel_url, force_refresh, final_start_date, stop_pad=False
    ):
        """The Videos tab, stopping after the page that reaches a video
        older than ``final_start_date``.

        The early-stop compares APPROXIMATE dates. When the pipeline will
        hydrate (stop_pad), the boundary is padded by each date's own
        rounding error ("3 years ago" ≈ ±6 months) so near-boundary videos
        on later pages still reach the exact check.
        """

        def older_than_start(videos):
            for video in videos:
                published = video.get("publish_date")
                if not published:
                    continue
                boundary = final_start_date
                if stop_pad:
                    boundary = boundary - approx_date_resolution(
                        video.get("publish_date_text")
                    )
                if published.date() < boundary:
                    return True
            return False

        yield from self._get_raw_tab_generator(
            channel_url,
            "videos",
            force_refresh,
            stop_after=older_than_start if final_start_date else None,
        )

    def get_channel_videos(
        self,
        channel_url,
        force_refresh=False,
        fetch_full_metadata=False,
        start_date=None,
        end_date=None,
        filters=None,
        stop_at_video_id=None,
        max_videos=-1,
    ):
        """
        Fetches videos from a YouTube channel's videos and shorts tab.

        Args:
            channel_url: The URL of the channel's videos page.
            force_refresh: Whether to bypass the cache and fetch fresh data.
            fetch_full_metadata: Whether to fetch full metadata for each video.
            start_date: The start date for filtering videos.
            end_date: The end date for filtering videos.
            filters: A dictionary of filter conditions.
            stop_at_video_id: The ID of the video to stop fetching at.
            max_videos: The maximum number of videos to fetch (-1 for all).

        Returns:
            A generator of video dictionaries.
        """
        validate_filters(filters, kind="video")
        validate_youtube_url(channel_url)
        channel_url = self._tab_url(channel_url, "videos")
        filters, final_start_date, final_end_date = build_date_filter(
            start_date, end_date, filters
        )
        # Pad the pagination early-stop only when the pipeline will
        # hydrate — that's when an exact post-merge check exists to
        # tighten what the padded boundary lets through.
        will_hydrate = fetch_full_metadata or any(
            k not in FAST_VIDEO_FILTERS for k in (filters or {})
        )
        raw_video_generator = self._get_raw_channel_videos_generator(
            channel_url, force_refresh, final_start_date, stop_pad=will_hydrate
        )
        return _run_filtered_pipeline(
            raw_video_generator,
            filters=filters,
            content_type="videos",
            fetch_full_metadata=fetch_full_metadata,
            video_fetcher=self.video_fetcher,
            logger=self.logger,
            stop_at_video_id=stop_at_video_id,
            max_videos=max_videos,
        )

    def get_videos_published_between(
        self,
        channel_url,
        start_date,
        end_date=None,
        force_refresh=False,
        margin=3,
    ):
        """Videos published in an exact window, found by bisecting the
        chronological listing with probe hydrations (~2·log₂ n) instead
        of hydrating every video in the padded window. See the facade
        docstring for the request-cost rationale.

        ``margin`` extra items are hydrated on each side of the bisected
        boundaries — channel listings are only approximately
        chronological (premieres, pinned items), so the final
        exact-date membership check runs over a slightly widened slice.
        """
        if start_date is None:
            raise ValueError(
                "start_date is required — an open-ended start would paginate "
                "the whole channel. Use get_channel_videos for that."
            )

        def norm(bound):
            if isinstance(bound, str):
                from .date_utils import parse_relative_date_string

                return parse_relative_date_string(bound)
            return bound

        def day_of(bound):
            return bound.date() if isinstance(bound, datetime) else bound

        start, end = norm(start_date), norm(end_date)
        start_day, end_day = day_of(start), day_of(end) if end else None
        validate_youtube_url(channel_url)
        channel_url = self._tab_url(channel_url, "videos")
        # Arguments are checked above, at call time; the requests start
        # on first iteration.
        return self._iter_published_between(
            channel_url, force_refresh, margin, start, end, start_day, end_day
        )

    def _iter_published_between(
        self, channel_url, force_refresh, margin, start, end, start_day, end_day
    ):

        raw = list(
            self._get_raw_channel_videos_generator(
                channel_url, force_refresh, start_day, stop_pad=True
            )
        )
        if not raw:
            return

        condition = {"gte": start}
        if end is not None:
            condition["lte"] = end

        hydrated: dict[str, dict] = {}

        def hydrate(i):
            video = raw[i]
            vid = video["video_id"]
            if vid not in hydrated:
                # One failed probe used to abort the whole window search.
                # Fall back to the listing record (approximate date), as
                # _process_videos does for the same errors.
                try:
                    full = self.video_fetcher.get_video_metadata(
                        f"https://www.youtube.com/watch?v={vid}"
                    )
                except (VideoUnavailableError, MetadataParsingError) as e:
                    self.logger.error(
                        "Error fetching metadata for video_id %s: %s", vid, e
                    )
                    full = None
                hydrated[vid] = _merge_hydrated(video, full) if full else dict(video)
            return hydrated[vid]

        def probe_day(i):
            """Exact calendar day of raw[i] (falls back to the
            approximate date if the watch page had none)."""
            merged = hydrate(i)
            dt = merged.get("publish_date") or raw[i].get("publish_date")
            if dt is None:
                return None
            return dt.date() if isinstance(dt, datetime) else dt

        n = len(raw)
        # raw is newest-first: days are (approximately) non-increasing.
        # Upper boundary: first index with day <= end_day.
        if end_day is None:
            i0 = 0
        else:
            lo, hi = 0, n
            while lo < hi:
                mid = (lo + hi) // 2
                d = probe_day(mid)
                if d is not None and d > end_day:
                    lo = mid + 1
                else:
                    hi = mid
            i0 = lo
        # Lower boundary: first index with day < start_day (exclusive end).
        lo, hi = i0, n
        while lo < hi:
            mid = (lo + hi) // 2
            d = probe_day(mid)
            if d is None or d >= start_day:
                lo = mid + 1
            else:
                hi = mid
        i1 = lo

        for i in range(max(0, i0 - margin), min(n, i1 + margin)):
            merged = hydrate(i)
            if merged.get("publish_date") is None:
                continue
            if apply_filters(merged, {"publish_date": condition}):
                yield merged

    def get_channel_shorts(
        self,
        channel_url,
        force_refresh=False,
        fetch_full_metadata=False,
        filters=None,
        stop_at_video_id=None,
        max_videos=-1,
    ):
        """
        Fetches shorts from a YouTube channel's shorts tab.

        Args:
            channel_url (str): The URL of the channel's shorts page.
            force_refresh (bool): Whether to bypass the cache and fetch fresh data.
            fetch_full_metadata (bool): Whether to fetch full metadata for each short.
            filters (Optional[dict]): A dictionary of filter conditions.
            stop_at_video_id (Optional[str]): The ID of the short to stop fetching at.
            max_videos (int): The maximum number of shorts to fetch (-1 for all).

        Returns:
            Generator[dict, None, None]: A generator of short dictionaries.
        """
        validate_filters(filters, kind="video")
        validate_youtube_url(channel_url)
        return _run_filtered_pipeline(
            self._get_raw_tab_generator(channel_url, "shorts", force_refresh),
            filters=filters,
            content_type="shorts",
            fetch_full_metadata=fetch_full_metadata,
            video_fetcher=self.video_fetcher,
            logger=self.logger,
            stop_at_video_id=stop_at_video_id,
            max_videos=max_videos,
        )

    def get_channel_streams(
        self,
        channel_url,
        force_refresh=False,
        fetch_full_metadata=False,
        filters=None,
        stop_at_video_id=None,
        max_videos=-1,
    ):
        """
        Fetches live streams from a channel's Live (``/streams``) tab —
        the tab that holds live, upcoming/scheduled, and past live
        content, which the Videos tab does NOT include.

        Items use the same shape as get_channel_videos. Upcoming streams
        carry ``is_upcoming=True`` and ``scheduled_text`` (the listing's
        "Scheduled for ..." text); set ``fetch_full_metadata=True`` to
        also get the precise ``scheduled_start_time`` and ``status`` from
        each stream's watch page.

        Args:
            channel_url: The channel URL (the ``/streams`` suffix is added
                automatically if absent).
            force_refresh: Bypass the cache and fetch fresh data.
            fetch_full_metadata: Fetch full per-stream metadata.
            filters: A dictionary of filter conditions.
            stop_at_video_id: The ID of the stream to stop fetching at.
            max_videos: The maximum number of streams to fetch (-1 for all).

        Returns:
            A generator of stream dictionaries.
        """
        validate_filters(filters, kind="video")
        validate_youtube_url(channel_url)
        channel_url = self._tab_url(channel_url, "streams")
        return _run_filtered_pipeline(
            self._get_raw_tab_generator(channel_url, "streams", force_refresh),
            filters=filters,
            content_type="videos",
            fetch_full_metadata=fetch_full_metadata,
            video_fetcher=self.video_fetcher,
            logger=self.logger,
            stop_at_video_id=stop_at_video_id,
            max_videos=max_videos,
        )


class PlaylistFetcher(_BaseFetcher):
    """Fetches data related to a YouTube playlist."""

    def __init__(
        self,
        session: httpx.Client,
        cache: MutableMapping | None,
        video_fetcher: VideoFetcher,
    ):
        super().__init__(session, cache, video_fetcher)

    def _get_playlist_page_data(
        self, playlist_id: str, require_ytcfg: bool = True
    ) -> tuple[dict, dict | None]:
        # Playlist pages are not cached (a playlist's contents change).
        return self._fetch_page(
            f"https://www.youtube.com/playlist?list={playlist_id}",
            what="playlist page",
            require_ytcfg=require_ytcfg,
            playlist_id=playlist_id,
        )

    def get_playlist_metadata(self, playlist_id: str) -> dict:
        """Fetch and parse a playlist's own metadata (title, author,
        description, video_count, ...). Wired in 0.8.0 — the parser
        existed with tests but was unreachable from the facade."""
        initial_data, _ = self._get_playlist_page_data(
            playlist_id, require_ytcfg=False
        )
        return parsing.parse_playlist_metadata(initial_data)

    def _get_raw_playlist_videos_generator(self, playlist_id: str):
        initial_data, ytcfg = self._get_playlist_page_data(playlist_id)
        # Resolve the item list shape-agnostically: YouTube migrated the
        # playlist listing from playlistVideoListRenderer/playlistVideoRenderer
        # to a bare lockupViewModel list (same migration that broke the
        # channel Videos tab in 0.6.0).
        items = parsing.get_playlist_item_list(initial_data)
        if not items:
            self.logger.warning(
                "No video renderers found on the initial playlist page: %s", playlist_id
            )
            return
        yield from self._paginate(
            items, ytcfg, parsing.extract_videos_from_playlist_items
        )

    def get_playlist_videos(
        self,
        playlist_id,
        fetch_full_metadata=False,
        start_date=None,
        end_date=None,
        filters=None,
        stop_at_video_id=None,
        max_videos=-1,
    ):
        """
        Fetches videos from a YouTube playlist.

        Handles pagination and filtering. Date filtering is FAST on
        playlists: the current lockup listing carries approximate
        relative dates ("2 years ago"), which is what the filter
        compares against. Pass ``fetch_full_metadata=True`` when you
        need precise publish dates; if the listing shape ever lacks a
        date, the filter is deferred to the per-video metadata rather
        than dropping the item (M-e).

        Args:
            playlist_id (str): The ID of the playlist.
            fetch_full_metadata (bool): Whether to fetch full metadata for each video.
            start_date (Optional[Union[str, date]]): The start date for filtering.
            end_date (Optional[Union[str, date]]): The end date for filtering.
            filters (Optional[dict]): A dictionary of filter conditions.
            stop_at_video_id (Optional[str]): The ID of the video to stop fetching at.
            max_videos (int): The maximum number of videos to fetch (-1 for all).

        Returns:
            Generator[dict, None, None]: A generator of video dictionaries.
        """
        validate_filters(filters, kind="video")
        filters, _, _ = build_date_filter(start_date, end_date, filters)
        return _run_filtered_pipeline(
            self._get_raw_playlist_videos_generator(playlist_id),
            filters=filters,
            content_type="videos",
            fetch_full_metadata=fetch_full_metadata,
            video_fetcher=self.video_fetcher,
            logger=self.logger,
            stop_at_video_id=stop_at_video_id,
            max_videos=max_videos,
        )
