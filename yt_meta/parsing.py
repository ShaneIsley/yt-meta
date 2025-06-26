"""
This module contains pure functions for parsing data from YouTube's HTML and JSON structures.
"""

import json
import logging
import re
from typing import Optional

from .exceptions import MetadataParsingError, VideoUnavailableError
from .utils import _deep_get

logger = logging.getLogger(__name__)

# Regex patterns adopted from the parent youtube-comment-downloader library
# for proven robustness.
YT_CFG_RE = r"ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;"
YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|(?:var\s+)?ytInitialData)\s*=\s*({.+?});'
YT_INITIAL_PLAYER_RESPONSE_RE = r'(?:window\s*\[\s*["\']ytInitialPlayerResponse["\']\s*\]|(?:var\s+)?ytInitialPlayerResponse)\s*=\s*({.+?});'


def _regex_search(text: str, pattern: str, default: str = "", flags: int = 0) -> str:
    """Helper to run a regex search and return the first group or a default."""
    match = re.search(pattern, text, flags)
    return match.group(1) if match else default


def find_ytcfg(html: str) -> Optional[dict]:
    """
    Finds and parses the `ytcfg` data from a page's HTML source.

    This data contains important context for making subsequent API requests,
    such as the INNERTUBE_API_KEY and client version.
    """
    match = re.search(r"ytcfg\.set\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("Failed to parse ytcfg JSON.")
            return None
    logger.warning("Could not find ytcfg data in HTML.")
    return None


def extract_and_parse_json(html_content: str, variable_name: str) -> Optional[dict]:
    """
    Extracts and parses a JSON object assigned to a JavaScript variable in HTML content.
    """
    # Use the proven, robust regex for the known complex YouTube variables.
    if variable_name == "ytInitialData":
        pattern = YT_INITIAL_DATA_RE
    elif variable_name == "ytInitialPlayerResponse":
        pattern = YT_INITIAL_PLAYER_RESPONSE_RE
    else:
        # Use a simpler, more generic pattern for other variables (e.g., in tests).
        logger.warning(
            f"Using generic regex for '{variable_name}'. This is less robust and intended for simple cases."
        )
        pattern = rf'var\s+{re.escape(variable_name)}\s*=\s*({{.*?}});'

    json_str = _regex_search(html_content, pattern, flags=re.DOTALL)
    if not json_str:
        logger.warning(
            f"Could not find JSON for '{variable_name}' using its designated regex."
        )
        return None

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON for '{variable_name}': {e}")
        return None


def parse_duration(duration_label: str) -> int | None:
    """
    Parses a human-readable duration label into a total number of seconds.

    Example:
        "11 minutes, 6 seconds" -> 666
    """
    if not duration_label:
        return None

    parts = duration_label.split(",")
    total_seconds = 0
    for part in parts:
        part = part.strip()
        if "hour" in part:
            total_seconds += int(part.split(" ")[0]) * 3600
        elif "minute" in part:
            total_seconds += int(part.split(" ")[0]) * 60
        elif "second" in part:
            total_seconds += int(part.split(" ")[0])
    return total_seconds if total_seconds > 0 else None


def parse_view_count(view_count_text: str) -> int | None:
    """
    Parses a view count string (e.g., '2,905,010 views') into an integer.
    """
    if not view_count_text:
        return None
    try:
        return int(view_count_text.split(" ")[0].replace(",", ""))
    except (ValueError, TypeError, IndexError):
        return None


def find_like_count(player_response_data: dict) -> int | None:
    """
    Extracts the like count from the `ytInitialPlayerResponse` data structure.
    """
    try:
        renderer = _deep_get(player_response_data, "microformat.playerMicroformatRenderer", {})
        like_count_str = renderer.get("likeCount")
        if like_count_str and isinstance(like_count_str, str) and like_count_str.isdigit():
            return int(like_count_str)
        return None
    except (KeyError, TypeError):
        logger.debug("Could not find like count in player response data.")
        return None


def find_heatmap(initial_data: dict) -> list | None:
    """
    Finds the video's "Most replayed" heatmap data from the `ytInitialData`.

    This data is located within the `frameworkUpdates` part of the initial data.
    """
    try:
        mutations = _deep_get(initial_data, "frameworkUpdates.entityBatchUpdate.mutations", [])
        for mutation in mutations:
            if "payload" in mutation and "macroMarkersListEntity" in mutation["payload"]:
                markers_list = _deep_get(
                    mutation,
                    "payload.macroMarkersListEntity.markersList.0.value.macroMarkersMarkersListRenderer.contents",
                    [],
                )
                heatmap = []
                for marker in markers_list:
                    if "marker" in marker and "heatmapMarker" in marker["marker"]:
                        heatmap_marker = marker["marker"]["heatmapMarker"]
                        heatmap.append(
                            {
                                "startMillis": _deep_get(
                                    heatmap_marker,
                                    "timeRangeStartMarker.markerDurationFromStartMillis",
                                ),
                                "durationMillis": _deep_get(heatmap_marker, "markerDurationMillis"),
                                "intensityScoreNormalized": _deep_get(heatmap_marker, "intensityScoreNormalized"),
                            }
                        )
                return heatmap
    except (KeyError, TypeError, IndexError):
        logger.debug("Could not find heatmap data in initial data.")
        return None


def extract_videos_from_renderers(renderers: list) -> tuple[list, str | None]:
    """
    Parses a list of video renderers from a channel's "Videos" tab.

    This function iterates through a list of renderer items, extracts the
    relevant information for each video, and finds the continuation token for
    paginating to the next set of results.

    Args:
        renderers: A list of renderer dictionaries from the channel page's data.

    Returns:
        A tuple containing:
        - A list of dictionaries, where each dict is a simplified video object.
        - A continuation token string for the next page, or None if not found.
    """
    videos = []
    continuation_token = None
    if not renderers:
        return videos, continuation_token

    for renderer in renderers:
        if "richItemRenderer" in renderer:
            video_data = _deep_get(renderer, "richItemRenderer.content.videoRenderer")
            if not video_data:
                continue

            badges = _deep_get(video_data, "badges", [])
            overlays = _deep_get(video_data, "thumbnailOverlays", [])
            is_members_only = any(
                _deep_get(b, "metadataBadgeRenderer.style") == "BADGE_STYLE_TYPE_MEMBERS_ONLY" for b in badges
            )
            is_live = any("thumbnailOverlayNowPlayingRenderer" in o for o in overlays)
            is_premiere = any(
                _deep_get(o, "thumbnailOverlayTimeStatusRenderer.text.runs.0.text") == "PREMIERE" for o in overlays
            )
            is_verified = any(
                _deep_get(b, "metadataBadgeRenderer.style") == "BADGE_STYLE_TYPE_VERIFIED"
                for b in _deep_get(video_data, "ownerBadges", [])
            )

            videos.append(
                {
                    "videoId": video_data.get("videoId"),
                    "title": _deep_get(video_data, "title.runs.0.text"),
                    "descriptionSnippet": _deep_get(video_data, "descriptionSnippet.runs.0.text"),
                    "thumbnails": _deep_get(video_data, "thumbnail.thumbnails", []),
                    "publishedTimeText": _deep_get(video_data, "publishedTimeText.simpleText"),
                    "lengthSeconds": parse_duration(
                        _deep_get(
                            video_data,
                            "lengthText.accessibility.accessibilityData.label",
                        )
                    ),
                    "viewCount": parse_view_count(_deep_get(video_data, "viewCountText.simpleText")),
                    "url": f"https://www.youtube.com{_deep_get(video_data, 'navigationEndpoint.commandMetadata.webCommandMetadata.url')}",  # noqa: E501
                    "isLive": is_live,
                    "isPremiere": is_premiere,
                    "isMembersOnly": is_members_only,
                    "isVerified": is_verified,
                }
            )

        if "continuationItemRenderer" in renderer:
            continuation_token = _deep_get(
                renderer,
                "continuationItemRenderer.continuationEndpoint.continuationCommand.token",
            )

    return videos, continuation_token


def extract_videos_from_playlist_renderer(renderer: dict) -> tuple[list, str | None]:
    """
    Parses a `playlistVideoListRenderer` from a playlist page.

    This function iterates through the contents of the renderer, extracts
    video data, and finds the continuation token for pagination.

    Args:
        renderer: A `playlistVideoListRenderer` dictionary from the page's data.

    Returns:
        A tuple containing:
        - A list of dictionaries, where each dict is a simplified video object.
        - A continuation token string for the next page, or None if not found.
    """
    videos = []
    continuation_token = None
    if not renderer or "contents" not in renderer:
        return videos, continuation_token

    renderer_list = renderer["contents"]

    for item in renderer_list:
        if "playlistVideoRenderer" in item:
            videos.append(parse_video_renderer(item["playlistVideoRenderer"]))
        elif "continuationItemRenderer" in item:
            continuation_endpoint = _deep_get(item, "continuationItemRenderer.continuationEndpoint")
            if continuation_endpoint and "continuationCommand" in continuation_endpoint:
                continuation_token = _deep_get(continuation_endpoint, "continuationCommand.token")
            # Fallback for the case where it's nested deeper
            elif continuation_endpoint and "commandExecutorCommand" in continuation_endpoint:
                for command in _deep_get(continuation_endpoint, "commandExecutorCommand.commands", []):
                    if "continuationCommand" in command:
                        continuation_token = _deep_get(command, "continuationCommand.token")
                        break

    return videos, continuation_token


def parse_video_renderer(renderer: dict) -> dict:
    """
    Parses a `videoRenderer` object into a simplified, flat dictionary.
    """
    if not renderer or not isinstance(renderer, dict):
        return None

    video_id = renderer.get("videoId")
    if not video_id:
        return None

    badges = _deep_get(renderer, "badges", [])
    is_live = any("LIVE" in b.get("metadataBadgeRenderer", {}).get("label", "") for b in badges)
    is_premiere = "PREMIERE" in _deep_get(renderer, "upcomingEventData.upcomingEventText.runs.0.text", "")

    view_count_text = _deep_get(renderer, "viewCountText.simpleText")
    if not view_count_text:
        # Sometimes it's in a different format
        view_count_text = _deep_get(renderer, "viewCountText.runs.0.text")

    return {
        "video_id": video_id,
        "title": _deep_get(renderer, "title.runs.0.text"),
        "description_snippet": _deep_get(renderer, "descriptionSnippet.runs.0.text"),
        "thumbnails": _deep_get(renderer, "thumbnail.thumbnails", []),
        "channel_name": _deep_get(renderer, "longBylineText.runs.0.text"),
        "channel_url": _deep_get(
            renderer,
            "longBylineText.runs.0.navigationEndpoint.commandMetadata.webCommandMetadata.url",
        ),
        "duration_seconds": parse_duration(
            _deep_get(renderer, "lengthText.accessibility.accessibilityData.label")
        ),
        "view_count": parse_view_count(view_count_text),
        "published_time_text": _deep_get(renderer, "publishedTimeText.simpleText"),
        "is_live": is_live,
        "is_premiere": is_premiere,
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def parse_channel_metadata(initial_data: dict) -> dict:
    """
    Parses the main metadata for a channel from the initial page data.
    """
    metadata_renderer = _deep_get(initial_data, "metadata.channelMetadataRenderer")
    if not metadata_renderer:
        logger.warning("Could not find channelMetadataRenderer in page data.")
        raise MetadataParsingError("Could not find channelMetadataRenderer in page data.")

    vanity_url_path = (
        "contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer.endpoint.browseEndpoint.canonicalBaseUrl"  # noqa: E501
    )
    vanity_handle = _deep_get(initial_data, vanity_url_path)
    vanity_url = (
        f"https://www.youtube.com{vanity_handle}" if vanity_handle else metadata_renderer.get("vanityChannelUrl")
    )

    return {
        "title": metadata_renderer.get("title"),
        "description": metadata_renderer.get("description"),
        "channel_id": metadata_renderer.get("externalId"),
        "vanity_url": vanity_url,
        "keywords": [kw.strip() for kw in metadata_renderer.get("keywords", "").split(",") if kw.strip()],
        "is_family_safe": metadata_renderer.get("isFamilySafe"),
    }


def parse_playlist_metadata(initial_data: dict) -> dict:
    """
    Parses the main metadata for a playlist from the `ytInitialData` object.
    """
    header = _deep_get(initial_data, "header.playlistHeaderRenderer")
    microformat = _deep_get(initial_data, "microformat.microformatDataRenderer")
    sidebar_primary = _deep_get(
        initial_data, "sidebar.playlistSidebarRenderer.items.0.playlistSidebarPrimaryInfoRenderer"
    )
    sidebar_secondary = _deep_get(
        initial_data, "sidebar.playlistSidebarRenderer.items.1.playlistSidebarSecondaryInfoRenderer"
    )

    video_count_text = _deep_get(sidebar_primary, "stats.0.runs.0.text", "").replace(",", "")
    playlist_id = None
    if microformat and "urlCanonical" in microformat:
        match = re.search(r"list=([^&]+)", microformat["urlCanonical"])
        if match:
            playlist_id = match.group(1)

    author = _deep_get(sidebar_secondary, "videoOwner.videoOwnerRenderer.title.runs.0.text")
    if not author:
        author = _deep_get(header, "ownerText.runs.0.text")

    return {
        "title": _deep_get(microformat, "title"),
        "author": author,
        "description": _deep_get(microformat, "description"),
        "video_count": int(video_count_text) if video_count_text.isdigit() else 0,
        "playlist_id": playlist_id,
    }


def parse_video_metadata(player_response_data: dict, initial_data: dict) -> dict:
    """
    Parses comprehensive video metadata from the `ytInitialPlayerResponse`
    and `ytInitialData` objects from a video's watch page.
    """
    if not player_response_data and not initial_data:
        logger.error("Could not extract playerResponse or initialData from page.")
        raise VideoUnavailableError("Could not extract playerResponse or initialData from page.")

    video_details = _deep_get(player_response_data, "videoDetails", {})
    microformat = _deep_get(player_response_data, "microformat.playerMicroformatRenderer", {})

    return {
        "video_id": video_details.get("videoId"),
        "title": video_details.get("title"),
        "channel_name": video_details.get("author"),
        "channel_id": video_details.get("channelId"),
        "duration_seconds": int(video_details.get("lengthSeconds", 0)),
        "view_count": int(video_details.get("viewCount", 0)),
        "publish_date": microformat.get("publishDate"),
        "upload_date": microformat.get("uploadDate"),
        "category": microformat.get("category"),
        "like_count": find_like_count(player_response_data),
        "keywords": video_details.get("keywords", []),
        "thumbnails": _deep_get(video_details, "thumbnail.thumbnails", []),
        "is_live": video_details.get("isLiveContent", False),
        "full_description": video_details.get("shortDescription"),
        "heatmap": find_heatmap(initial_data),
        "subscriber_count_text": _deep_get(
            initial_data,
            "contents.twoColumnWatchNextResults.results.results.contents.1.videoSecondaryInfoRenderer.owner.videoOwnerRenderer.subscriberCountText.simpleText",
        ),
    }
