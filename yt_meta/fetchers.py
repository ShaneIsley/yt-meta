from typing import MutableMapping, Optional, TYPE_CHECKING
import logging
import dateparser

from httpx import Client

from . import parsing
from .date_utils import parse_relative_date_string
from .exceptions import MetadataParsingError, VideoUnavailableError
from .filtering import apply_filters, partition_filters
from .utils import _deep_get
from .validators import validate_filters

if TYPE_CHECKING:
    from .fetchers import VideoFetcher

logger = logging.getLogger(__name__)

class _BaseFetcher:
    """A base class for fetchers that process lists of videos."""
    def __init__(self, session: Client, cache: Optional[MutableMapping], video_fetcher: "VideoFetcher"):
        self.session = session
        self.cache = cache
        self.video_fetcher = video_fetcher
        self.logger = logger

    def _process_videos_generator(self, video_generator, must_fetch_full_metadata, fast_filters, slow_filters, stop_at_video_id, max_videos):
        videos_processed = 0
        for video in video_generator:
            if not apply_filters(video, fast_filters):
                continue
            merged_video = video
            if must_fetch_full_metadata:
                try:
                    video_url = f"https://www.youtube.com/watch?v={video['video_id']}"
                    full_meta = self.video_fetcher.get_video_metadata(video_url)
                    if full_meta:
                        merged_video = {**video, **full_meta}
                    else:
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
                return
            if max_videos != -1 and videos_processed >= max_videos:
                return

    def _get_continuation_data(self, token: str, ytcfg: dict):
        cache_key = f"continuation:{token}"
        if cache_key in self.cache:
            self.logger.info(f"Cache hit for continuation token: {token[:10]}...")
            return self.cache[cache_key]
        data = {"context": ytcfg["INNERTUBE_CONTEXT"], "continuation": token}
        response = self.session.post(f"https://www.youtube.com/youtubei/v1/browse?key={ytcfg['INNERTUBE_API_KEY']}", json=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        self.cache[cache_key] = result
        return result

class VideoFetcher:
    """Fetches data related to a single YouTube video."""
    def __init__(self, session: Client, cache: Optional[MutableMapping]):
        self.session = session
        self.cache = cache

    def get_video_metadata(self, youtube_url: str) -> dict:
        """
        Fetches and parses comprehensive metadata for a given YouTube video.

        Args:
            youtube_url: The full URL of the YouTube video.

        Returns:
            A dictionary containing detailed video metadata.
        """
        logger.info(f"Fetching video page: {youtube_url}")
        video_id = youtube_url.split("v=")[-1]
        cache_key = f"video_meta:{video_id}"
        if cache_key in self.cache:
            logger.info(f"Cache hit for video metadata: {video_id}")
            return self.cache[cache_key]

        try:
            response = self.session.get(youtube_url, timeout=10)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            logger.error(f"Failed to fetch video page {youtube_url}: {e}")
            raise VideoUnavailableError(f"Failed to fetch video page: {e}", video_id=youtube_url.split("v=")[-1]) from e

        player_response_data = parsing.extract_and_parse_json(html, "ytInitialPlayerResponse")
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")

        if not player_response_data or not initial_data:
            logger.warning(
                f"Could not extract metadata for video {video_id}. "
                "The page structure may have changed or the video is unavailable. Skipping."
            )
            return None

        result = parsing.parse_video_metadata(player_response_data, initial_data)
        self.cache[cache_key] = result
        return result

    def get_video_id(self, youtube_url: str) -> str:
        # Basic parsing of video ID from URL
        if "v=" in youtube_url:
            return youtube_url.split("v=")[1].split("&")[0]
        # Handle shorts URLs
        if "/shorts/" in youtube_url:
            return youtube_url.split("/shorts/")[1].split("?")[0]
        raise ValueError(f"Could not extract video ID from URL: {youtube_url}")

class ChannelFetcher(_BaseFetcher):
    """Fetches data related to a YouTube channel's videos and shorts."""
    def __init__(self, session: Client, cache: Optional[MutableMapping], video_fetcher: VideoFetcher):
        super().__init__(session, cache, video_fetcher)

    def _get_channel_page_cache_key(self, channel_url: str) -> str:
        key = channel_url.rstrip("/")
        if not key.endswith("/videos"):
            key += "/videos"
        return f"channel_page:{key}"

    def _get_channel_shorts_page_cache_key(self, channel_url: str) -> str:
        key = channel_url.rstrip("/")
        if not key.endswith("/shorts"):
            key += "/shorts"
        return f"channel_shorts_page:{key}"

    def _get_channel_page_data(self, channel_url: str, force_refresh: bool = False) -> tuple[dict, dict, str]:
        key = self._get_channel_page_cache_key(channel_url)
        if not force_refresh and key in self.cache:
            self.logger.info(f"Using cached data for channel: {key}")
            return self.cache[key]
        try:
            self.logger.info(f"Fetching channel page: {key}")
            response = self.session.get(key.replace("channel_page:", ""), timeout=10)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            self.logger.error(f"Request failed for channel page {key}: {e}")
            raise VideoUnavailableError(f"Could not fetch channel page: {e}", channel_url=key) from e
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        if not initial_data:
            raise MetadataParsingError("Could not extract ytInitialData from channel page.", channel_url=key)
        ytcfg = parsing.find_ytcfg(html)
        if not ytcfg:
            raise MetadataParsingError("Could not extract ytcfg from channel page.", channel_url=key)
        self.logger.info(f"Caching data for channel: {key}")
        result = (initial_data, ytcfg, html)
        self.cache[key] = result
        return result

    def _get_channel_shorts_page_data(self, channel_url: str, force_refresh: bool = False) -> tuple[dict, dict, str]:
        key = self._get_channel_shorts_page_cache_key(channel_url)
        if not force_refresh and key in self.cache:
            return self.cache[key]
        try:
            response = self.session.get(key.replace("channel_shorts_page:", ""), timeout=10)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            raise VideoUnavailableError(f"Could not fetch channel shorts page: {e}", channel_url=key) from e
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        if not initial_data:
            raise MetadataParsingError("Could not extract ytInitialData from channel shorts page.", channel_url=key)
        ytcfg = parsing.find_ytcfg(html)
        if not ytcfg:
            raise MetadataParsingError("Could not extract ytcfg from channel shorts page.", channel_url=key)
        result = (initial_data, ytcfg, html)
        self.cache[key] = result
        return result

    def get_channel_metadata(self, channel_url: str, force_refresh: bool = False) -> dict:
        initial_data, _, _ = self._get_channel_page_data(channel_url, force_refresh=force_refresh)
        return parsing.parse_channel_metadata(initial_data)

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
                return _deep_get(renderer, "continuationItemRenderer.continuationEndpoint.continuationCommand.token")
        return None

    def _get_video_renderers_from_data(self, continuation_data: dict):
        return _deep_get(continuation_data, "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems", [])

    def _get_continuation_token_from_data(self, continuation_data: dict):
        continuation_items = self._get_video_renderers_from_data(continuation_data)
        for item in continuation_items:
            if "continuationItemRenderer" in item:
                return _deep_get(item, "continuationItemRenderer.continuationEndpoint.continuationCommand.token")
        return None

    def _get_raw_channel_videos_generator(self, channel_url, force_refresh, final_start_date):
        try:
            initial_data, ytcfg, _ = self._get_channel_page_data(channel_url, force_refresh=force_refresh)
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
                if final_start_date and video.get("publish_date"):
                    video_publish_date = video["publish_date"]
                    if video_publish_date and video_publish_date.date() < final_start_date:
                        stop_pagination = True
                yield video
            if stop_pagination or not continuation_token:
                break
            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                break
            continuation_token = self._get_continuation_token_from_data(continuation_data)
            renderers = self._get_video_renderers_from_data(continuation_data)

    def _get_raw_shorts_generator(self, channel_url, force_refresh):
        try:
            initial_data, ytcfg, _ = self._get_channel_shorts_page_data(channel_url, force_refresh=force_refresh)
        except VideoUnavailableError as e:
            self.logger.error("Could not fetch initial channel shorts page: %s", e)
            return
        if not initial_data:
            raise MetadataParsingError("Could not find initial data script in channel shorts page")

        tabs = _deep_get(initial_data, "contents.twoColumnBrowseResultsRenderer.tabs", [])
        shorts_tab_renderer = None
        for tab in tabs:
            if _deep_get(tab, "tabRenderer.title") == "Shorts":
                shorts_tab_renderer = _deep_get(tab, "tabRenderer")
                break
        if not shorts_tab_renderer:
            raise MetadataParsingError("Could not find 'Shorts' tab renderer on the page.", channel_url=channel_url)

        renderers = _deep_get(shorts_tab_renderer, "content.richGridRenderer.contents", [])
        continuation_token = self._get_continuation_token(shorts_tab_renderer)

        while True:
            stop_pagination = False
            for renderer in renderers:
                if "richItemRenderer" not in renderer:
                    continue
                video_data = _deep_get(renderer, "richItemRenderer.content.shortsLockupViewModel")
                if not video_data:
                    continue
                video = parsing.extract_shorts_from_renderers([renderer])[0][0]
                if video:
                    yield video

            if stop_pagination or not continuation_token:
                break

            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                break

            continuation_token = self._get_continuation_token_from_data(continuation_data)
            renderers = self._get_video_renderers_from_data(continuation_data)

    def get_channel_videos(self, channel_url, force_refresh=False, fetch_full_metadata=False, start_date=None, end_date=None, filters=None, stop_at_video_id=None, max_videos=-1):
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
        validate_filters(filters)
        if not channel_url.endswith("/videos"):
            channel_url = f"{channel_url.rstrip('/')}/videos"
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
        raw_video_generator = self._get_raw_channel_videos_generator(channel_url, force_refresh, final_start_date)
        yield from self._process_videos_generator(video_generator=raw_video_generator, must_fetch_full_metadata=must_fetch_full_metadata, fast_filters=fast_filters, slow_filters=slow_filters, stop_at_video_id=stop_at_video_id, max_videos=max_videos)

    def get_channel_shorts(self, channel_url, force_refresh=False, fetch_full_metadata=False, filters=None, stop_at_video_id=None, max_videos=-1):
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
        validate_filters(filters)
        if filters is None:
            filters = {}
        fast_filters, slow_filters = partition_filters(filters)
        must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)
        if slow_filters and not fetch_full_metadata:
            self.logger.warning(f"Slow filters {list(slow_filters.keys())} provided without fetch_full_metadata=True. Full metadata will be fetched.")
        raw_shorts_generator = self._get_raw_shorts_generator(channel_url, force_refresh)
        yield from self._process_videos_generator(video_generator=raw_shorts_generator, must_fetch_full_metadata=must_fetch_full_metadata, fast_filters=fast_filters, slow_filters=slow_filters, stop_at_video_id=stop_at_video_id, max_videos=max_videos)

class PlaylistFetcher(_BaseFetcher):
    """Fetches data related to a YouTube playlist."""
    def __init__(self, session: Client, cache: Optional[MutableMapping], video_fetcher: VideoFetcher):
        super().__init__(session, cache, video_fetcher)

    def _get_raw_playlist_videos_generator(self, playlist_id: str):
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        try:
            response = self.session.get(playlist_url, timeout=10)
            response.raise_for_status()
            html = response.text
        except Exception as e:
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

    def get_playlist_videos(self, playlist_id, fetch_full_metadata=False, start_date=None, end_date=None, filters=None, stop_at_video_id=None, max_videos=-1):
        """
        Fetches videos from a YouTube playlist.

        Handles pagination and filtering. Note that date filtering for playlists
        is a "slow" operation and will trigger a full metadata fetch for each video.

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
        validate_filters(filters)
        if not filters:
            filters = {}
        if start_date:
            filters["publish_date"] = (">=", start_date)
        if end_date:
            if "publish_date" in filters:
                existing_op, existing_date = filters["publish_date"]
                if existing_op == ">=":
                    filters["publish_date"] = ("between", (existing_date, end_date))
            else:
                filters["publish_date"] = ("<=", end_date)
        fast_filters, slow_filters = partition_filters(filters)
        yield from self._process_videos_generator(
            video_generator=self._get_raw_playlist_videos_generator(playlist_id),
            must_fetch_full_metadata=fetch_full_metadata or bool(slow_filters),
            fast_filters=fast_filters,
            slow_filters=slow_filters,
            stop_at_video_id=stop_at_video_id,
            max_videos=max_videos,
        ) 