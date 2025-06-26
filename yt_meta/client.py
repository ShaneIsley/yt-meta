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
            if stop_at_video_id and video["video_id"] == stop_at_video_id:
                self.logger.info("Found video %s, stopping.", stop_at_video_id)
                return

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

    def _get_raw_playlist_videos_generator(self, playlist_id: str) -> Generator[dict, None, None]:
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        try:
            response = self.session.get(playlist_url, timeout=10)
            response.raise_for_status()
            html = response.text
        except requests.exceptions.RequestException as e:
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
        if not channel_url.endswith("/videos"):
            channel_url = f"{channel_url.rstrip('/')}/videos"

        self.logger.info(f"Fetching videos for channel: {channel_url}, Filters: {filters}, Start: {start_date}, End: {end_date}")

        if filters is None:
            filters = {}

        publish_date_from_filter = filters.get("publish_date", {})
        start_date_from_filter = publish_date_from_filter.get("gt") or publish_date_from_filter.get("gte")
        end_date_from_filter = publish_date_from_filter.get("lt") or publish_date_from_filter.get("lte")
        final_start_date = start_date or start_date_from_filter
        final_end_date = end_date or end_date_from_filter

        if isinstance(final_start_date, str):
            final_start_date = parse_relative_date_string(final_start_date)
        if isinstance(final_end_date, str):
            final_end_date = parse_relative_date_string(final_end_date)
        
        date_filter_conditions = {}
        if final_start_date:
            date_filter_conditions["gte"] = final_start_date
        if final_end_date:
            date_filter_conditions["lte"] = final_end_date
        if date_filter_conditions:
            filters["publish_date"] = date_filter_conditions

        fast_filters, slow_filters = partition_filters(filters)
        must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)
        if slow_filters and not fetch_full_metadata:
            self.logger.warning(f"Slow filters {list(slow_filters.keys())} provided without fetch_full_metadata=True. Full metadata will be fetched.")

        raw_video_generator = self._get_raw_channel_videos_generator(
            channel_url, force_refresh, final_start_date
        )

        yield from self._process_videos_generator(
            video_generator=raw_video_generator,
            must_fetch_full_metadata=must_fetch_full_metadata,
            fast_filters=fast_filters,
            slow_filters=slow_filters,
            stop_at_video_id=stop_at_video_id,
            max_videos=max_videos,
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
        self.logger.info(f"Fetching videos for playlist: {playlist_id}, Filters: {filters}, Start: {start_date}, End: {end_date}")

        if filters is None:
            filters = {}

        publish_date_from_filter = filters.get("publish_date", {})
        start_date_from_filter = publish_date_from_filter.get("gt") or publish_date_from_filter.get("gte")
        end_date_from_filter = publish_date_from_filter.get("lt") or publish_date_from_filter.get("lte")
        final_start_date = start_date or start_date_from_filter
        final_end_date = end_date or end_date_from_filter

        if isinstance(final_start_date, str):
            final_start_date = parse_relative_date_string(final_start_date)
        if isinstance(final_end_date, str):
            final_end_date = parse_relative_date_string(final_end_date)

        date_filter_conditions = {}
        if final_start_date:
            date_filter_conditions["gte"] = final_start_date
        if final_end_date:
            date_filter_conditions["lte"] = final_end_date
        if date_filter_conditions:
            filters["publish_date"] = date_filter_conditions

        fast_filters, slow_filters = partition_filters(filters)
        must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)
        if slow_filters and not fetch_full_metadata:
            self.logger.warning(f"Slow filters {list(slow_filters.keys())} provided without fetch_full_metadata=True. Full metadata will be fetched.")

        raw_video_generator = self._get_raw_playlist_videos_generator(playlist_id)

        yield from self._process_videos_generator(
            video_generator=raw_video_generator,
            must_fetch_full_metadata=must_fetch_full_metadata,
            fast_filters=fast_filters,
            slow_filters=slow_filters,
            stop_at_video_id=stop_at_video_id,
            max_videos=max_videos,
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
