# yt_meta/client.py

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional, Union, Generator

import requests
from youtube_comment_downloader.downloader import YoutubeCommentDownloader

from . import parsing
from .date_utils import parse_relative_date_string
from .exceptions import MetadataParsingError, VideoUnavailableError
from .filtering import (
    apply_filters,
    partition_filters,
)
from .utils import _deep_get

logger = logging.getLogger(__name__)


class YtMetaClient(YoutubeCommentDownloader):
    """
    A client for fetching metadata for YouTube videos, channels, and playlists.

    This class provides methods to retrieve detailed information such as titles,
    descriptions, view counts, and publication dates. It handles the complexity
    of YouTube's internal data structures and pagination logic (continuations),
    offering a simple interface for data collection.

    It also includes an in-memory cache for channel pages to improve performance
    for repeated requests.
    """

    def __init__(self):
        super().__init__()
        self._channel_page_cache = {}
        self.logger = logger

    def clear_cache(self, channel_url: str = None):
        """
        Clears the in-memory cache for channel pages.

        If a `channel_url` is provided, only the cache for that specific
        channel is cleared. Otherwise, the entire cache is cleared.
        """
        if channel_url:
            key = channel_url.rstrip("/")
            if not key.endswith("/videos"):
                key += "/videos"

            if key in self._channel_page_cache:
                del self._channel_page_cache[key]
                self.logger.info(f"Cache cleared for channel: {key}")
        else:
            self._channel_page_cache.clear()
            self.logger.info("Entire channel page cache cleared.")

    def _get_channel_page_data(self, channel_url: str, force_refresh: bool = False) -> tuple[dict, dict, str]:
        """
        Internal method to fetch, parse, and cache the initial data from a channel's "Videos" page.
        """
        key = channel_url.rstrip("/")
        if not key.endswith("/videos"):
            key += "/videos"

        if not force_refresh and key in self._channel_page_cache:
            self.logger.info(f"Using cached data for channel: {key}")
            return self._channel_page_cache[key]

        try:
            self.logger.info(f"Fetching channel page: {key}")
            response = self.session.get(key, timeout=10)
            response.raise_for_status()
            html = response.text
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for channel page {key}: {e}")
            raise VideoUnavailableError(f"Could not fetch channel page: {e}", channel_url=key) from e

        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        if not initial_data:
            self.logger.error("Failed to extract ytInitialData from channel page.")
            raise MetadataParsingError(
                "Could not extract ytInitialData from channel page.",
                channel_url=key,
            )

        ytcfg = parsing.find_ytcfg(html)
        if not ytcfg:
            self.logger.error("Failed to extract ytcfg from channel page.")
            raise MetadataParsingError("Could not extract ytcfg from channel page.", channel_url=key)

        self.logger.info(f"Caching data for channel: {key}")
        self._channel_page_cache[key] = (initial_data, ytcfg, html)
        return initial_data, ytcfg, html

    def get_channel_metadata(self, channel_url: str, force_refresh: bool = False) -> dict:
        """
        Fetches and parses metadata for a given YouTube channel.

        Args:
            channel_url: The URL of the channel's main page or "Videos" tab.
            force_refresh: If True, bypasses the in-memory cache.

        Returns:
            A dictionary containing channel metadata.
        """
        initial_data, _, _ = self._get_channel_page_data(channel_url, force_refresh=force_refresh)
        return parsing.parse_channel_metadata(initial_data)

    def get_video_metadata(self, youtube_url: str) -> dict:
        """
        Fetches and parses comprehensive metadata for a given YouTube video.

        Args:
            youtube_url: The full URL of the YouTube video.

        Returns:
            A dictionary containing detailed video metadata.
        """
        try:
            self.logger.info(f"Fetching video page: {youtube_url}")
            response = self.session.get(youtube_url, timeout=10)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            self.logger.error(f"Failed to fetch video page {youtube_url}: {e}")
            raise VideoUnavailableError(f"Failed to fetch video page: {e}", video_id=youtube_url.split("v=")[-1]) from e

        player_response_data = parsing.extract_and_parse_json(html, "ytInitialPlayerResponse")
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")

        if not player_response_data or not initial_data:
            video_id = youtube_url.split("v=")[-1]
            logger.warning(
                f"Could not extract metadata for video {video_id}. "
                "The page structure may have changed or the video is unavailable. Skipping."
            )
            return None

        return parsing.parse_video_metadata(player_response_data, initial_data)

    def get_channel_videos(
        self,
        channel_url: str,
        force_refresh: bool = False,
        fetch_full_metadata: bool = False,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        filters: Optional[dict] = None,
    ) -> Generator[dict, None, None]:
        """
        A generator that yields metadata for all videos on a channel's "Videos" tab.

        This method efficiently fetches videos page by page and can be configured
        to stop paginating early based on date, which is useful for channels
        with a very large number of videos.

        It also supports a powerful two-stage filtering system:
        1.  **Fast Filters**: Applied first on basic metadata (e.g., title, view count).
        2.  **Slow Filters**: Applied on full metadata for videos that pass the first
            stage (e.g., like count). This requires `fetch_full_metadata=True` or
            for a slow filter to be present in the `filters` dict.

        Note:
            Using a "slow" filter (e.g., `like_count`, `publish_date`) or setting
            `fetch_full_metadata=True` will trigger an additional network request
            for every video that passes the initial fast filters, which can be
            significantly slower.

        Args:
            channel_url: The URL of the channel's "Videos" tab.
            force_refresh: If True, bypasses the cache for the initial page load.
            fetch_full_metadata: If True, fetches the complete metadata for each video.
                This is slower as it requires an additional request per video.
            start_date: The earliest date for videos to include. Can be a date object
                or a string (e.g., "1d", "2 weeks ago").
            end_date: The latest date for videos to include. Can be a date object
                or a string.
            filters: A dictionary of filters to apply to the videos.

        Yields:
            Dictionaries of video metadata. The contents depend on the
            `fetch_full_metadata` flag.
        """
        self.logger.info("Starting to fetch videos for channel: %s", channel_url)

        if filters is None:
            filters = {}

        # --- Date Processing & Filter Setup ---
        publish_date_from_filter = filters.get("publish_date", {})
        
        start_date_from_filter = publish_date_from_filter.get("gt") or publish_date_from_filter.get("gte")
        end_date_from_filter = publish_date_from_filter.get("lt") or publish_date_from_filter.get("lte")

        # Prioritize dedicated arguments and resolve to final date objects
        final_start_date = start_date or start_date_from_filter
        final_end_date = end_date or end_date_from_filter

        if isinstance(final_start_date, str):
            final_start_date = parse_relative_date_string(final_start_date)
        if isinstance(final_end_date, str):
            final_end_date = parse_relative_date_string(final_end_date)
        
        # 3. Create/update the 'publish_date' filter to enforce the final dates
        date_filter_conditions = {}
        if final_start_date:
            date_filter_conditions["gte"] = final_start_date
        if final_end_date:
            date_filter_conditions["lte"] = final_end_date
        
        if date_filter_conditions:
            # This ensures that start_date/end_date args are always enforced by apply_filters
            filters["publish_date"] = date_filter_conditions

        # 4. Now partition all filters
        fast_filters, slow_filters = partition_filters(filters)
        
        # Use a consistent end_date for pagination logic, defaulting to today
        pagination_end_date = final_end_date or datetime.today().date()

        # Determine if we need to enter the slow path for any video
        must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)

        if must_fetch_full_metadata and slow_filters:
            self.logger.info(
                f"Slow filter(s) detected: {list(slow_filters.keys())}. "
                "Fetching full metadata for videos, which may be slow."
            )

        initial_data, ytcfg, html = self._get_channel_page_data(channel_url, force_refresh)
        if not initial_data or not ytcfg:
            raise MetadataParsingError(
                "Could not find initial data script in channel page",
                channel_url=channel_url,
            )

        tabs = _deep_get(initial_data, "contents.twoColumnBrowseResultsRenderer.tabs", [])
        videos_tab = next((tab for tab in tabs if _deep_get(tab, "tabRenderer.selected")), None)
        if not videos_tab:
            raise MetadataParsingError("Could not find videos tab in channel page.", channel_url=channel_url)

        renderers = _deep_get(videos_tab, "tabRenderer.content.richGridRenderer.contents", [])
        if not renderers:
            self.logger.warning("No video renderers found on the initial channel page: %s", channel_url)
            return

        videos, continuation_token = parsing.extract_videos_from_renderers(renderers)

        while True:
            # Yield videos that are within the date range
            for video in videos:
                # --- Stage 1: Apply Fast Filters (including estimated date) ---
                if not apply_filters(video, fast_filters):
                    continue

                # --- Stage 2: Fetch Full Metadata and Apply Slow/Precise Filters ---
                if must_fetch_full_metadata:
                    try:
                        full_meta = self.get_video_metadata(video["watchUrl"])
                        if full_meta:
                            merged_video = {**video, **full_meta}
                        else:
                            # If fetching full metadata fails, log it and skip the video
                            # to avoid filtering on incomplete data.
                            self.logger.warning(
                                f"Skipping video {video['videoId']} due to missing full metadata."
                            )
                            continue
                    except VideoUnavailableError as e:
                        self.logger.warning(f"Skipping video {video['videoId']}: {e}")
                        continue
                else:
                    merged_video = video

                # --- Apply All Filters ---
                if not apply_filters(merged_video, filters):
                    continue

                yield merged_video

            if not continuation_token:
                self.logger.info("Terminating video fetch loop.")
                break

            # Fetch the next page
            self.logger.info("Fetching next page of videos with continuation token.")
            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                self.logger.warning("Stopping pagination due to missing continuation data.")
                break

            renderers = _deep_get(
                continuation_data,
                "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems",
                [],
            )
            videos, continuation_token = parsing.extract_videos_from_renderers(renderers)

    def get_playlist_videos(
        self,
        playlist_id: str,
        fetch_full_metadata: bool = False,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        filters: Optional[dict] = None,
    ) -> Generator[dict, None, None]:
        """
        A generator that yields metadata for all videos in a playlist.

        It supports a powerful two-stage filtering system:
        1.  **Fast Filters**: Applied first on basic metadata (e.g., title, view count).
        2.  **Slow Filters**: Applied on full metadata for videos that pass the first
            stage (e.g., like count). This requires `fetch_full_metadata=True` or
            for a slow filter to be present in the `filters` dict.

        Note:
            Unlike channel video fetching, playlist fetching cannot be stopped
            early based on date, as playlists are not guaranteed to be in
            chronological order. Using a "slow" filter (like `publish_date`)
            will require fetching all videos in the playlist.

        Args:
            playlist_id: The ID of the playlist.
            fetch_full_metadata: If True, fetches the full, detailed metadata for each video.
            start_date: The earliest date for videos to include. Can be a date object
                or a string (e.g., "1d", "2 weeks ago").
            end_date: The latest date for videos to include. Can be a date object
                or a string.
            filters: A dictionary of filters to apply to the videos.

        Yields:
            Dictionaries of video metadata. The contents depend on the
            `fetch_full_metadata` flag.
        """
        self.logger.info("Starting to fetch videos for playlist: %s", playlist_id)

        if filters is None:
            filters = {}

        # --- Date Processing & Filter Setup ---
        publish_date_from_filter = filters.get("publish_date", {})
        
        start_date_from_filter = publish_date_from_filter.get("gt") or publish_date_from_filter.get("gte")
        end_date_from_filter = publish_date_from_filter.get("lt") or publish_date_from_filter.get("lte")

        # Prioritize dedicated arguments and resolve to final date objects
        final_start_date = start_date or start_date_from_filter
        final_end_date = end_date or end_date_from_filter

        if isinstance(final_start_date, str):
            final_start_date = parse_relative_date_string(final_start_date)
        if isinstance(final_end_date, str):
            final_end_date = parse_relative_date_string(final_end_date)

        # 3. Create/update the 'publish_date' filter to enforce the final dates
        date_filter_conditions = {}
        if final_start_date:
            date_filter_conditions["gte"] = final_start_date
        if final_end_date:
            date_filter_conditions["lte"] = final_end_date

        if date_filter_conditions:
            # This ensures that start_date/end_date args are always enforced by apply_filters
            filters["publish_date"] = date_filter_conditions

        # 4. Now partition all filters
        fast_filters, slow_filters = partition_filters(filters)

        # Use a consistent end_date for pagination logic, defaulting to today
        pagination_end_date = final_end_date or datetime.today().date()

        # Determine if we need to enter the slow path for any video
        must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)

        if must_fetch_full_metadata and slow_filters:
            self.logger.info(
                f"Slow filter(s) detected: {list(slow_filters.keys())}. "
                "Fetching full metadata for videos, which may be slow."
            )

        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

        try:
            self.logger.info(f"Fetching playlist page: {playlist_url}")
            response = self.session.get(playlist_url, timeout=10)
            response.raise_for_status()
            html = response.text
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for playlist page {playlist_url}: {e}")
            raise VideoUnavailableError(f"Could not fetch playlist page: {e}", playlist_id=playlist_id) from e

        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        if not initial_data:
            raise MetadataParsingError("Could not extract ytInitialData from playlist page.", playlist_id=playlist_id)

        ytcfg = parsing.find_ytcfg(html)
        if not ytcfg:
            raise MetadataParsingError("Could not extract ytcfg from playlist page.", playlist_id=playlist_id)

        path_to_renderer = "contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer.content.sectionListRenderer.contents.0.itemSectionRenderer.contents.0.playlistVideoListRenderer"
        renderer = _deep_get(initial_data, path_to_renderer)

        if not renderer:
            # Fallback for slightly different structures that can sometimes occur.
            path_to_renderer = "contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer.content.sectionListRenderer.contents.0.playlistVideoListRenderer"
            renderer = _deep_get(initial_data, path_to_renderer)

        if not renderer:
            self.logger.warning("No video renderers found on the initial playlist page: %s", playlist_id)
            return

        videos, continuation_token = parsing.extract_videos_from_playlist_renderer(
            renderer
        )

        while True:
            # Yield videos that pass filters
            for video in videos:
                # --- Stage 1: Apply Fast Filters ---
                if not apply_filters(video, fast_filters):
                    continue
                
                # --- Stage 2: Fetch Full Metadata and Apply Slow/Precise Filters ---
                if must_fetch_full_metadata:
                    try:
                        full_meta = self.get_video_metadata(video["watchUrl"])
                        if full_meta:
                            merged_video = {**video, **full_meta}
                        else:
                            # If fetching full metadata fails, log it and skip the video
                            # to avoid filtering on incomplete data.
                            self.logger.warning(
                                f"Skipping video {video['videoId']} due to missing full metadata."
                            )
                            continue
                    except VideoUnavailableError as e:
                        self.logger.warning(
                            f"Skipping video {video['videoId']} due to being unavailable: {e}"
                        )
                        continue
                else:
                    # If we passed the fast stage and don't need full metadata, yield basic video
                    yield video

            if not continuation_token:
                self.logger.info("Terminating video fetch loop.")
                break

            # Fetch the next page
            self.logger.info("Fetching next page of videos with continuation token.")
            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                self.logger.warning(
                    "Stopping pagination due to missing continuation data."
                )
                break

            renderers = _deep_get(
                continuation_data,
                "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems",
                [],
            )
            temp_renderer = {"contents": renderers}
            videos, continuation_token = parsing.extract_videos_from_playlist_renderer(
                temp_renderer
            )

    def _get_continuation_data(self, token: str, ytcfg: dict):
        """Fetches the next page of videos using a continuation token."""
        try:
            payload = {
                "context": {
                    "client": {
                        "clientName": _deep_get(ytcfg, "INNERTUBE_CONTEXT.client.clientName"),
                        "clientVersion": _deep_get(ytcfg, "INNERTUBE_CONTEXT.client.clientVersion"),
                    },
                    "user": {
                        "lockedSafetyMode": _deep_get(ytcfg, "INNERTUBE_CONTEXT.user.lockedSafetyMode"),
                    },
                    "request": {
                        "useSsl": _deep_get(ytcfg, "INNERTUBE_CONTEXT.request.useSsl"),
                    },
                },
                "continuation": token,
            }
            api_key = _deep_get(ytcfg, "INNERTUBE_API_KEY")

            self.logger.debug("Making continuation request to youtubei/v1/browse.")
            response = self.session.post(
                f"https://www.youtube.com/youtubei/v1/browse?key={api_key}",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self.logger.error("Failed to fetch continuation data: %s", e)
            return None
