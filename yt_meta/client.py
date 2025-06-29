# yt_meta/client.py

import logging
from datetime import date, datetime
from typing import Optional, Union, Generator, MutableMapping

import httpx

from . import parsing
from .date_utils import parse_relative_date_string
from .exceptions import MetadataParsingError, VideoUnavailableError
from .filtering import (
    apply_filters,
    apply_comment_filters,
)
from .fetchers import VideoFetcher, ChannelFetcher, PlaylistFetcher
from .comment_fetcher import CommentFetcher
from .utils import _deep_get
from .validators import validate_filters

logger = logging.getLogger(__name__)


class YtMeta:
    """
    A client for fetching metadata for YouTube videos, channels, playlists, and comments.
    This class acts as a Facade, delegating calls to specialized fetcher classes.
    """

    def __init__(self, cache: Optional[MutableMapping] = None):
        self.cache = {} if cache is None else cache
        self.logger = logger
        self.session = httpx.Client()
        self._video_fetcher = VideoFetcher(self.session, self.cache)
        self._channel_fetcher = ChannelFetcher(self.session, self.cache, self._video_fetcher)
        self._playlist_fetcher = PlaylistFetcher(self.session, self.cache, self._video_fetcher)
        self._comment_fetcher = CommentFetcher()

    def clear_cache(self, prefix: Optional[str] = None):
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

    def get_channel_metadata(self, channel_url: str, force_refresh: bool = False) -> dict:
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

    def get_channel_videos(
        self,
        channel_url: str,
        force_refresh: bool = False,
        fetch_full_metadata: bool = False,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        filters: Optional[dict] = None,
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
            channel_url, force_refresh, fetch_full_metadata, start_date, end_date, filters, stop_at_video_id, max_videos
        )

    def get_playlist_videos(
        self,
        playlist_id: str,
        fetch_full_metadata: bool = False,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        filters: Optional[dict] = None,
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
            playlist_id, fetch_full_metadata, start_date, end_date, filters, stop_at_video_id, max_videos
        )

    def get_channel_shorts(
        self,
        channel_url: str,
        force_refresh: bool = False,
        fetch_full_metadata: bool = False,
        filters: Optional[dict] = None,
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
            channel_url, force_refresh, fetch_full_metadata, filters, stop_at_video_id, max_videos
        )

    def get_video_comments(
        self,
        youtube_url: str,
        sort_by: str = "top",
        limit: int = -1,
        filters: Optional[dict] = None,
    ) -> Generator[dict, None, None]:
        """
        Fetches comments for a given YouTube video.

        Args:
            youtube_url: The full URL of the YouTube video.
            sort_by: How to sort comments. 'top' (default) or 'recent'.
            limit: The maximum number of comments to return (-1 for all).
            filters: A dictionary specifying the filter conditions.

        Yields:
            A dictionary for each comment with a standardized structure.
        """
        video_id = self._video_fetcher.get_video_id(youtube_url)
        comments_generator = self._comment_fetcher.get_comments(video_id, sort_by=sort_by)
        
        # Apply filters if any
        if filters:
            validate_filters(filters)
            comments_generator = apply_comment_filters(comments_generator, filters)

        # Apply limit if any
        if limit > 0:
            for i, comment in enumerate(comments_generator):
                if i >= limit:
                    break
                yield comment
        else:
            yield from comments_generator

    def _get_videos_tab_renderer(self, initial_data: dict):
        tabs = _deep_get(initial_data, "contents.twoColumnBrowseResultsRenderer.tabs", [])
        for tab in tabs:
            if _deep_get(tab, "tabRenderer.selected"):
                return _deep_get(tab, "tabRenderer")
        return None

    def _get_video_renderers(self, tab_renderer: dict):
        return _deep_get(tab_renderer, "content.richGridRenderer.contents", [])

    def _get_continuation_token(self, tab_renderer: dict):
        renderers = self._get_video_renderers(tab_renderer)
        for renderer in renderers:
            if "continuationItemRenderer" in renderer:
                return _deep_get(
                    renderer,
                    "continuationItemRenderer.continuationEndpoint.continuationCommand.token",
                )
        return None

    def _get_video_renderers_from_data(self, continuation_data: dict):
        return _deep_get(
            continuation_data,
            "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems",
            [],
        )

    def _get_continuation_token_from_data(self, continuation_data: dict):
        continuation_items = self._get_video_renderers_from_data(continuation_data)
        for item in continuation_items:
            if "continuationItemRenderer" in item:
                return _deep_get(
                    item,
                    "continuationItemRenderer.continuationEndpoint.continuationCommand.token",
                )
        return None

    def _process_videos_generator(
        self,
        video_generator: Generator[dict, None, None],
        must_fetch_full_metadata: bool,
        fast_filters: dict,
        slow_filters: dict,
        stop_at_video_id: str | None,
        max_videos: int,
    ) -> Generator[dict, None, None]:
        videos_processed = 0
        for video in video_generator:
            if not apply_filters(video, fast_filters):
                continue

            merged_video = video
            if must_fetch_full_metadata:
                try:
                    video_url = f"https://www.youtube.com/watch?v={video['video_id']}"
                    full_meta = self.get_video_metadata(video_url)
                    if full_meta:
                        merged_video = {**video, **full_meta}
                    else:
                        self.logger.warning("Could not fetch full metadata for video_id: %s", video["video_id"])
                        if slow_filters:
                            continue
                except (VideoUnavailableError, MetadataParsingError) as e:
                    self.logger.error("Error fetching metadata for video_id %s: %s", video["video_id"], e)
                    continue

            if not apply_filters(merged_video, slow_filters):
                continue

            yield merged_video
            videos_processed += 1

            if stop_at_video_id and video["video_id"] == stop_at_video_id:
                self.logger.info("Found video %s, stopping.", stop_at_video_id)
                return

            if max_videos != -1 and videos_processed >= max_videos:
                self.logger.info("Reached max_videos limit of %s.", max_videos)
                return

    def _get_raw_channel_videos_generator(
        self,
        channel_url: str,
        force_refresh: bool,
        final_start_date: Optional[date],
    ) -> Generator[dict, None, None]:
        try:
            initial_data, ytcfg, _ = self._get_channel_page_data(
                channel_url, force_refresh=force_refresh
            )
        except VideoUnavailableError as e:
            self.logger.error("Could not fetch initial channel page: %s", e)
            return

        if not initial_data:
            raise MetadataParsingError("Could not find initial data script in channel page")

        tab_renderer = self._get_videos_tab_renderer(initial_data)
        if not tab_renderer:
            raise MetadataParsingError("Could not find videos tab renderer in channel page")

        continuation_token = self._get_continuation_token(tab_renderer)
        renderers = self._get_video_renderers(tab_renderer)

        while True:
            stop_pagination = False
            for renderer in renderers:
                if "richItemRenderer" not in renderer:
                    continue
                video_data = renderer["richItemRenderer"]["content"]
                if "videoRenderer" not in video_data:
                    continue
                video = parsing.parse_video_renderer(video_data["videoRenderer"])
                if not video:
                    continue

                if final_start_date and video.get("publish_date") and video["publish_date"] < final_start_date:
                    self.logger.info("Video %s is older than start_date %s. Stopping pagination.", video["video_id"], final_start_date)
                    stop_pagination = True
                    break
                yield video

            if stop_pagination or not continuation_token:
                break

            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                break

            continuation_token = self._get_continuation_token_from_data(continuation_data)
            renderers = self._get_video_renderers_from_data(continuation_data)

    def _get_raw_shorts_generator(self, channel_url: str, force_refresh: bool) -> Generator[dict, None, None]:
        try:
            initial_data, ytcfg, _ = self._get_channel_shorts_page_data(channel_url, force_refresh)
        except (VideoUnavailableError, MetadataParsingError) as e:
            self.logger.error("Could not fetch initial channel shorts page: %s", e)
            return

        tabs = _deep_get(initial_data, "contents.twoColumnBrowseResultsRenderer.tabs", [])
        shorts_tab = None
        for tab in tabs:
            if _deep_get(tab, "tabRenderer.title") == "Shorts":
                shorts_tab = tab
                break

        if not shorts_tab:
            # If there's only one tab and it's for shorts, it might not have the title check
            if len(tabs) == 1 and "/shorts" in _deep_get(tabs[0], "tabRenderer.endpoint.commandMetadata.webCommandMetadata.url", ""):
                 shorts_tab = tabs[0]
            else:
                raise MetadataParsingError("Could not find Shorts tab renderer.", channel_url=channel_url)


        renderers = _deep_get(shorts_tab, "tabRenderer.content.richGridRenderer.contents", [])

        shorts, continuation_token = parsing.extract_shorts_from_renderers(renderers)
        for short in shorts:
            yield short

        while continuation_token:
            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                break

            renderers = _deep_get(continuation_data, "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems", [])
            shorts, continuation_token = parsing.extract_shorts_from_renderers(renderers)
            for short in shorts:
                yield short

    def _get_raw_playlist_videos_generator(self, playlist_id: str) -> Generator[dict, None, None]:
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        try:
            response = self.session.get(playlist_url, timeout=10)
            response.raise_for_status()
            html = response.text
        except httpx.RequestError as e:
            raise VideoUnavailableError(f"Could not fetch playlist page: {e}", playlist_id=playlist_id) from e
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        if not initial_data:
            raise MetadataParsingError("Could not extract ytInitialData from playlist page.", playlist_id=playlist_id)

        ytcfg = parsing.find_ytcfg(html)
        if not ytcfg:
            raise MetadataParsingError("Could not extract ytcfg from playlist page.", playlist_id=playlist_id)

        path = "contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer.content.sectionListRenderer.contents.0.itemSectionRenderer.contents.0.playlistVideoListRenderer"
        renderer = _deep_get(initial_data, path)
        if not renderer:
            self.logger.warning("No video renderers found on the initial playlist page: %s", playlist_id)
            return

        videos, continuation_token = parsing.extract_videos_from_playlist_renderer(renderer)

        while True:
            yield from videos

            if not continuation_token:
                break

            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                break

            renderers = _deep_get(continuation_data, "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems", [])
            videos, continuation_token = parsing.extract_videos_from_playlist_renderer({"contents": renderers})

    def _get_continuation_data(self, token: str, ytcfg: dict):
        """
        Fetches the next batch of data using a continuation token.
        Caches the result based on the token.
        """
        cache_key = f"continuation:{token}"
        if cache_key in self.cache:
            self.logger.info(f"Cache hit for continuation token: {token[:10]}...")
            return self.cache[cache_key]
        data = {"context": ytcfg["INNERTUBE_CONTEXT"], "continuation": token}
        response = self.session.post(
            f"https://www.youtube.com/youtubei/v1/browse?key={ytcfg['INNERTUBE_API_KEY']}", 
            json=data, 
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        self.cache[cache_key] = result
        return result

    def _resolve_date(self, d: Optional[Union[str, date]]) -> Optional[date]:
        if isinstance(d, str):
            parsed_date = parse_relative_date_string(d)
            if parsed_date:
                return parsed_date.date()
            return datetime.fromisoformat(d).date()
        return d
