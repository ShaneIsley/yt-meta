# yt_meta/farmer.py

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Union

import requests
from youtube_comment_downloader.downloader import YoutubeCommentDownloader

from . import parsing
from .date_utils import parse_relative_date_string
from .exceptions import MetadataParsingError, VideoUnavailableError
from .utils import _deep_get

logger = logging.getLogger(__name__)


class YtMetaClient(YoutubeCommentDownloader):
    """
    Downloads metadata for YouTube videos and channels.
    """

    def __init__(self):
        super().__init__()
        self._channel_page_cache = {}
        self.logger = logger

    def clear_cache(self, channel_url: str = None):
        """
        Clears the internal cache. If a channel_url is provided, only that
        entry is cleared. Otherwise, the entire cache is cleared.
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
        if not channel_url.endswith("/videos"):
            channel_url = channel_url.rstrip("/") + "/videos"

        if not force_refresh and channel_url in self._channel_page_cache:
            self.logger.info(f"Using cached data for channel: {channel_url}")
            return self._channel_page_cache[channel_url]

        try:
            self.logger.info(f"Fetching channel page: {channel_url}")
            response = self.session.get(channel_url, timeout=10)
            response.raise_for_status()
            html = response.text
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for channel page {channel_url}: {e}")
            raise VideoUnavailableError(f"Could not fetch channel page: {e}", channel_url=channel_url) from e

        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        if not initial_data:
            self.logger.error("Failed to extract ytInitialData from channel page.")
            raise MetadataParsingError(
                "Could not extract ytInitialData from channel page.",
                channel_url=channel_url,
            )

        ytcfg = parsing.find_ytcfg(html)
        if not ytcfg:
            self.logger.error("Failed to extract ytcfg from channel page.")
            raise MetadataParsingError("Could not extract ytcfg from channel page.", channel_url=channel_url)

        self.logger.info(f"Caching data for channel: {channel_url}")
        self._channel_page_cache[channel_url] = (initial_data, ytcfg, html)
        return initial_data, ytcfg, html

    def get_channel_metadata(self, channel_url: str, force_refresh: bool = False) -> dict:
        """
        Fetches and parses metadata for a given YouTube channel.
        """
        initial_data, _, _ = self._get_channel_page_data(channel_url, force_refresh=force_refresh)
        return parsing.parse_channel_metadata(initial_data)

    def get_video_metadata(self, youtube_url: str) -> dict:
        """
        Fetches and parses comprehensive metadata for a given YouTube video.
        """
        try:
            self.logger.info(f"Fetching video page: {youtube_url}")
            response = self.session.get(youtube_url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            self.logger.error(f"Failed to fetch video page {youtube_url}: {e}")
            raise VideoUnavailableError(f"Failed to fetch video page: {e}", video_id=youtube_url.split("v=")[-1]) from e

        html = response.text

        player_response_data = parsing.extract_and_parse_json(html, "ytInitialPlayerResponse")
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        return parsing.parse_video_metadata(player_response_data, initial_data)

    def get_channel_videos(
        self,
        channel_url: str,
        force_refresh: bool = False,
        fetch_full_metadata: bool = False,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
    ):
        """
        A generator that yields metadata for all videos on a channel.

        Args:
            channel_url: The URL of the channel's "Videos" tab.
            force_refresh: If True, bypasses the cache for the initial page load.
            fetch_full_metadata: If True, fetches the full, detailed metadata for each video.
            start_date: The earliest date for videos to include. Can be a date object
                        or a string (e.g., "1d", "2 weeks ago").
            end_date: The latest date for videos to include. Can be a date object
                      or a string.
        """
        self.logger.info("Starting to fetch videos for channel: %s", channel_url)

        # --- Date Processing ---
        if isinstance(start_date, str):
            start_date = parse_relative_date_string(start_date)
        if isinstance(end_date, str):
            # For end_date, we just need to parse it if it's a string, no 'today' default needed.
            end_date = parse_relative_date_string(end_date)
        elif end_date is None:
            # Default end_date to today if not provided
            end_date = datetime.today().date()

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

        stop_pagination = False
        while True:
            # Check the last video on the page for the stop condition
            if videos and start_date:
                last_video = videos[-1]
                published_text = last_video.get("publishedTimeText")
                if published_text:
                    estimated_date = parse_relative_date_string(published_text)
                    # Rough check: if estimated date is more than 30 days older than start_date,
                    # we do a precise check to be sure. This avoids calls on very old pages.
                    if estimated_date < (start_date - timedelta(days=30)):
                        self.logger.info(
                            "Stopping pagination based on rough check. Last video published ~%s.",
                            estimated_date,
                        )
                        stop_pagination = True
                    else:  # Precise check needed
                        try:
                            last_video_meta = self.get_video_metadata(last_video["watchUrl"])
                            precise_date = datetime.fromisoformat(last_video_meta["publish_date"]).date()
                            if precise_date < start_date:
                                self.logger.info(
                                    "Stopping pagination based on precise check. Last video published on %s.",
                                    precise_date,
                                )
                                stop_pagination = True
                        except (VideoUnavailableError, KeyError):
                            self.logger.warning(
                                "Could not perform precise date check for video %s. Continuing.",
                                last_video.get("videoId"),
                            )

            # Yield videos that are within the date range
            for video in videos:
                if fetch_full_metadata:
                    try:
                        full_meta = self.get_video_metadata(video["watchUrl"])
                        publish_date_obj = datetime.fromisoformat(full_meta["publish_date"]).date()

                        if (not start_date or publish_date_obj >= start_date) and (
                            not end_date or publish_date_obj <= end_date
                        ):
                            yield full_meta

                    except (VideoUnavailableError, KeyError) as e:
                        self.logger.warning(
                            "Could not fetch full metadata for video %s: %s",
                            video.get("videoId"),
                            e,
                        )
                else:
                    # Without full metadata, we can't filter precisely.
                    # We will filter out videos that are clearly too old from the rough check.
                    published_text = video.get("publishedTimeText")
                    if published_text:
                        estimated_date = parse_relative_date_string(published_text)
                        if (not start_date or estimated_date >= start_date) and (
                            not end_date or estimated_date <= end_date
                        ):
                            yield video
                    else:  # if no date, yield it
                        yield video

            if stop_pagination or not continuation_token:
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

    def get_playlist_videos(self, playlist_id: str, fetch_full_metadata: bool = False):
        """
        A generator that yields metadata for all videos in a playlist.

        Args:
            playlist_id: The ID of the playlist.
            fetch_full_metadata: If True, fetches the full, detailed metadata for each video.
        """
        self.logger.info("Starting to fetch videos for playlist: %s", playlist_id)
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
            # Fallback for slightly different structures
            path_to_renderer = "contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer.content.sectionListRenderer.contents.0.playlistVideoListRenderer"
            renderer = _deep_get(initial_data, path_to_renderer)

        if not renderer:
            self.logger.warning("No video renderers found on the initial playlist page: %s", playlist_id)
            return

        videos, continuation_token = parsing.extract_videos_from_playlist_renderer(renderer)

        while True:
            for video in videos:
                if fetch_full_metadata:
                    try:
                        yield self.get_video_metadata(video["watchUrl"])
                    except (VideoUnavailableError, KeyError) as e:
                        self.logger.warning(
                            "Could not fetch full metadata for video %s: %s",
                            video.get("videoId"),
                            e,
                        )
                else:
                    yield video
            
            if not continuation_token:
                self.logger.info("Terminating video fetch loop.")
                break

            self.logger.info("Fetching next page of videos with continuation token.")
            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                self.logger.warning("Stopping pagination due to missing continuation data.")
                break
            
            # The path to renderers is different for playlist continuations
            renderers = _deep_get(
                continuation_data,
                "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems",
                [],
            )
            
            # For playlists, the continuation response contains a list of renderers directly
            # So we can't just use extract_videos_from_renderers.
            # We need a new function or adapt the existing one.
            # Let's adapt extract_videos_from_playlist_renderer to handle this
            
            # HACK: Create a temporary renderer structure to reuse the parsing function
            temp_renderer = {"contents": renderers}
            videos, continuation_token = parsing.extract_videos_from_playlist_renderer(temp_renderer)

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
