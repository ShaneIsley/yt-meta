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


def find_ytcfg(html: str) -> Optional[dict]:
    """
    Find and parse the ytcfg data from the page's HTML.

    This data contains important context for making API requests, such as the
    API key and client version.
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


def extract_and_parse_json(html: str, variable_name: str) -> dict | None:
    """
    Finds a javascript variable assignment, extracts the JSON blob, and parses it.
    """
    try:
        start_key = f"var {variable_name} = "
        start_index = html.find(start_key)
        if start_index == -1:
            logger.warning(f"Could not find JavaScript variable '{variable_name}'.")
            return None

        start_index += len(start_key)
        end_index = html.find("};", start_index)
        if end_index == -1:
            logger.warning(f"Could not find end of JSON for variable '{variable_name}'.")
            return None

        json_str = html[start_index : end_index + 1]
        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Failed to parse JSON for '{variable_name}': {e}")
        return None


def parse_duration(duration_label: str) -> int | None:
    """
    Parses a duration label like '11 minutes, 6 seconds' into total seconds.
    Handles hours, minutes, and seconds.
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
    Parses a view count string like '2,905,010 views' into an integer.
    """
    if not view_count_text:
        return None
    try:
        return int(view_count_text.split(" ")[0].replace(",", ""))
    except (ValueError, TypeError, IndexError):
        return None


def find_like_count(player_response_data: dict) -> int | None:
    """
    Finds the like count from the player response data.
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
    Finds the heatmap data by searching through the framework update mutations.
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
    """Helper to extract video data and a continuation token from a list of renderers."""
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
                    "watchUrl": f"https://www.youtube.com{_deep_get(video_data, 'navigationEndpoint.commandMetadata.webCommandMetadata.url')}",  # noqa: E501
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
    """Helper to extract video data and a continuation token from a playlistVideoListRenderer."""
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
    """Helper to parse a single video renderer from a playlist."""
    return {
        "videoId": renderer.get("videoId"),
        "title": _deep_get(renderer, "title.runs.0.text"),
        "thumbnails": _deep_get(renderer, "thumbnail.thumbnails", []),
        "lengthSeconds": parse_duration(_deep_get(renderer, "lengthText.accessibility.accessibilityData.label")),
        "watchUrl": f"https://www.youtube.com{_deep_get(renderer, 'navigationEndpoint.commandMetadata.webCommandMetadata.url')}",
    }


def parse_channel_metadata(initial_data: dict) -> dict:
    """
    Parses channel metadata from the initial data blob.
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
    Parses playlist metadata from the initial data blob.
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
    Parses video metadata from the player response and initial data blobs.
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
