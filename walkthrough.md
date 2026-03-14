# yt-meta Code Walkthrough

*2026-03-14T02:53:10Z by Showboat 0.6.1*
<!-- showboat-id: dfa1926c-c868-4261-90c5-68425c9492ff -->

## Overview

**yt-meta** is a Python library for scraping YouTube metadata without requiring an API key. It fetches video details, channel listings, playlist contents, comments, and transcripts by parsing YouTube's server-rendered HTML and internal JSON API endpoints.

The codebase follows a **facade pattern**: a single `YtMeta` client class delegates to specialized fetcher objects, each responsible for one domain (videos, channels, playlists, comments, transcripts). Supporting modules handle HTML/JSON parsing, result filtering, caching, and date utilities.

### Project structure

```
yt_meta/
├── __init__.py              # Package exports
├── client.py                # YtMeta facade — the public API
├── constants.py             # URL templates, regex patterns, API keys
├── exceptions.py            # Custom error hierarchy
├── utils.py                 # General-purpose helpers
├── date_utils.py            # Relative date parsing
├── caching.py               # DummyCache and SQLiteCache
├── parsing.py               # HTML scraping and JSON extraction
├── validators.py            # Filter schema and validation
├── filtering.py             # Two-stage filter engine
├── fetchers.py              # VideoFetcher, ChannelFetcher, PlaylistFetcher
├── comment_api_client.py    # Low-level comment API requests
├── comment_parser.py        # Comment JSON parsing
├── comment_fetcher.py       # Comment orchestration loop
└── transcript_fetcher.py    # Transcript retrieval
```

We will walk through these files bottom-up: foundations first, then the orchestration layer.

## 1. Package Exports (`__init__.py`)

The package's public API is defined in `__init__.py`. It re-exports the `YtMeta` client class and all custom exceptions, so users only need `from yt_meta import YtMeta`:

```bash
cat -n yt_meta/__init__.py
```

```output
     1	# yt_meta/__init__.py
     2	
     3	from .client import YtMeta
     4	from .comment_api_client import CommentAPIClient
     5	from .comment_fetcher import BestCommentFetcher, CommentFetcher
     6	from .comment_parser import CommentParser
     7	from .date_utils import parse_relative_date_string
     8	from .exceptions import MetadataParsingError, VideoUnavailableError
     9	
    10	__version__ = "0.3.1"
    11	
    12	__all__ = [
    13	    "YtMeta",
    14	    "MetadataParsingError",
    15	    "VideoUnavailableError",
    16	    "parse_relative_date_string",
    17	    "CommentFetcher",
    18	    "BestCommentFetcher",  # Backward compatibility
    19	    "CommentAPIClient",
    20	    "CommentParser",
    21	]
```

The \`__all__\` list exposes: the main \`YtMeta\` facade, both exception types, the date parser, and the comment subsystem classes (\`CommentFetcher\`, \`BestCommentFetcher\` as a backwards-compatible alias, \`CommentAPIClient\`, \`CommentParser\`). This gives advanced users access to the comment internals while keeping the typical use case simple.

## 2. Constants (`constants.py`)

This module defines the hardcoded values the scrapers depend on: URL templates for YouTube pages, regex patterns for extracting embedded JSON, and an internal API key used by comment fetching.

```bash
cat -n yt_meta/constants.py
```

```output
     1	"""
     2	Centralized constants for URLs, regex patterns, and API dictionary keys.
     3	"""
     4	
     5	# --- URLs and Regex ---
     6	YOUTUBE_VIDEO_URL = "https://www.youtube.com/watch?v={youtube_id}"
     7	YOUTUBE_API_URL = "https://www.youtube.com/youtubei/v1/next"
     8	USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36"
     9	
    10	YT_CFG_RE = r"ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;"
    11	YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'
    12	
    13	# --- YouTube API Keys ---
    14	
    15	# Root keys
    16	KEY_ENGAGEMENT_PANELS = "engagementPanels"
    17	KEY_FRAMEWORK_UPDATES = "frameworkUpdates"
    18	KEY_ON_RESPONSE_RECEIVED_ENDPOINTS = "onResponseReceivedEndpoints"
    19	
    20	# Command and Continuation keys
    21	KEY_CONTINUATION = "continuation"
    22	KEY_CONTINUATION_COMMAND = "continuationCommand"
    23	KEY_CONTINUATION_ENDPOINT = "continuationEndpoint"
    24	KEY_CONTINUATION_ITEM_RENDERER = "continuationItemRenderer"
    25	KEY_CONTINUATION_ITEMS = "continuationItems"
    26	KEY_APPEND_CONTINUATION_ITEMS_ACTION = "appendContinuationItemsAction"
    27	KEY_RELOAD_CONTINUATION_ITEMS_COMMAND = "reloadContinuationItemsCommand"
    28	KEY_SERVICE_ENDPOINT = "serviceEndpoint"
    29	KEY_SUB_MENU_ITEMS = "subMenuItems"
    30	KEY_SORT_FILTER_SUB_MENU_RENDERER = "sortFilterSubMenuRenderer"
    31	KEY_TOKEN = "token"
    32	
    33	# Comment structure keys
    34	KEY_COMMENT_ENTITY_PAYLOAD = "commentEntityPayload"
    35	KEY_COMMENT_REPLIES_RENDERER = "commentRepliesRenderer"
    36	KEY_COMMENT_RENDERER = "commentRenderer"
    37	KEY_COMMENT_THREAD_RENDERER = "commentThreadRenderer"
    38	KEY_PROPERTIES = "properties"
    39	KEY_TOOLBAR = "toolbar"
    40	KEY_REPLIES = "replies"
    41	
    42	# Comment author and metadata keys
    43	KEY_AUTHOR = "author"
    44	KEY_AUTHOR_BADGES = "authorBadges"
    45	KEY_AVATAR_THUMBNAIL_URL = "avatarThumbnailUrl"
    46	KEY_BADGE_RENDERER = "badgeRenderer"
    47	KEY_BROWSE_ENDPOINT = "browseEndpoint"
    48	KEY_CHANNEL_ID = "channelId"
    49	KEY_CHANNEL_RENDERER = "channelRenderer"
    50	KEY_DISPLAY_NAME = "displayName"
    51	KEY_ICON = "icon"
    52	KEY_ICON_TYPE = "iconType"
    53	KEY_IS_CREATOR = "isCreator"
    54	KEY_IS_PINNED = "isPinned"
    55	KEY_IS_VERIFIED = "isVerified"
    56	KEY_METADATA_BADGE_RENDERER = "metadataBadgeRenderer"
    57	KEY_NAVIGATION_ENDPOINT = "navigationEndpoint"
    58	KEY_OWNER_BADGES = "ownerBadges"
    59	KEY_REPLY_COUNT = "replyCount"
    60	
    61	# Content and text keys
    62	KEY_CONTENT = "content"
    63	KEY_CONTENT_TEXT = "contentText"  # Legacy key for some comments
    64	KEY_PUBLISHED_TIME = "publishedTime"
    65	KEY_RUNS = "runs"
    66	KEY_TEXT = "text"
    67	KEY_TITLE = "title"
    68	
    69	# Context and config keys
    70	KEY_CONTEXT = "context"
    71	KEY_INNERTUBE_API_KEY = "INNERTUBE_API_KEY"
    72	KEY_INNERTUBE_CONTEXT = "INNERTUBE_CONTEXT"
    73	
    74	# Miscellaneous
    75	KEY_MUTATIONS = "mutations"
    76	KEY_PAYLOAD = "payload"
    77	KEY_ENTITY_BATCH_UPDATE = "entityBatchUpdate"
    78	KEY_ENGAGEMENT_PANEL_SECTION_LIST_RENDERER = "engagementPanelSectionListRenderer"
    79	KEY_HEADER = "header"
    80	KEY_ENGAGEMENT_PANEL_TITLE_HEADER_RENDERER = "engagementPanelTitleHeaderRenderer"
    81	KEY_CONTENTS = "contents"
    82	KEY_MENU = "menu"
```

Key things to note:
- **\`YOUTUBE_VIDEO_URL\`** is the template for constructing watch page URLs from video IDs.
- **\`YOUTUBE_API_URL\`** points to YouTube's internal \`/youtubei/v1/next\` endpoint, used for fetching comments via POST requests.
- **\`YT_CFG_RE\`** and **\`YT_INITIAL_DATA_RE\`** are the regex patterns used by the parser to extract embedded JSON blobs from YouTube's HTML pages. These are the foundation of the entire scraping approach — YouTube embeds structured data as JavaScript variables in the page source.
- The rest of the file defines dictionary key constants for navigating YouTube's deeply nested JSON structures, organized by domain (comments, author metadata, content, etc.).

## 3. Exceptions (`exceptions.py`)

The library defines a small exception hierarchy. All errors inherit from \`YtMetaError\`, which carries optional context (video_id, channel_url, playlist_id) for easier debugging:

```bash
cat -n yt_meta/exceptions.py
```

```output
     1	"""Custom exceptions for the yt-meta library."""
     2	
     3	
     4	class YtMetaError(Exception):
     5	    """
     6	    Base exception for all errors raised by the yt-meta library.
     7	
     8	    This exception can store context like a `video_id` or `channel_url` to
     9	    make debugging easier.
    10	    """
    11	
    12	    def __init__(self, message, video_id=None, channel_url=None, playlist_id=None):
    13	        super().__init__(message)
    14	        self.video_id = video_id
    15	        self.channel_url = channel_url
    16	        self.playlist_id = playlist_id
    17	
    18	    def __str__(self):
    19	        details = []
    20	        if self.video_id:
    21	            details.append(f"video_id='{self.video_id}'")
    22	        if self.channel_url:
    23	            details.append(f"channel_url='{self.channel_url}'")
    24	        if self.playlist_id:
    25	            details.append(f"playlist_id='{self.playlist_id}'")
    26	
    27	        if details:
    28	            return f"{super().__str__()} ({', '.join(details)})"
    29	        return super().__str__()
    30	
    31	
    32	class MetadataParsingError(YtMetaError):
    33	    """
    34	    Raised when essential metadata cannot be found or parsed from the page.
    35	
    36	    This typically occurs if YouTube changes its page structure, and the
    37	    scraper can no longer find the `ytInitialData` or `ytcfg` JSON blobs.
    38	    """
    39	
    40	    pass
    41	
    42	
    43	class VideoUnavailableError(YtMetaError):
    44	    """
    45	    Raised when a video or channel page cannot be fetched.
    46	
    47	    This can be due to a network error, an invalid URL, or if the video
    48	    is private, deleted, or otherwise inaccessible.
    49	    """
    50	
    51	    pass
```

The \`__str__\` override on \`YtMetaError\` is a nice touch — it appends whichever context fields are present to the error message, so you get messages like \`"Could not parse metadata (video_id='abc123')"\` automatically. The two subclasses distinguish between parsing failures (YouTube changed its HTML structure) and fetch failures (network errors, private/deleted content).

## 4. Utilities (`utils.py`)

This module provides three critical helper functions used throughout the codebase. The most important is \`_deep_get()\`, which safely navigates YouTube's deeply nested JSON:

```bash
sed -n '1,60p' yt_meta/utils.py | cat -n
```

```output
     1	# yt_meta/utils.py
     2	
     3	
     4	def _deep_get(dictionary, keys, default=None):
     5	    """
     6	    Safely access nested dictionary keys and list indices.
     7	
     8	    This function allows you to retrieve a value from a nested structure of
     9	    dictionaries and lists using a dot-separated string of keys or a list
    10	    of keys/indices.
    11	
    12	    Args:
    13	        dictionary (dict or list): The nested structure to search.
    14	        keys (str or list): A dot-separated string (e.g., "a.b.0.c") or a
    15	                            list of keys and integer indices.
    16	        default: The value to return if any key is not found. Defaults to None.
    17	
    18	    Returns:
    19	        The value found at the specified path, or the default value if not found.
    20	    """
    21	    if dictionary is None:
    22	        return default
    23	    if not isinstance(keys, list):
    24	        keys = keys.split(".")
    25	
    26	    current_val = dictionary
    27	    for key in keys:
    28	        if isinstance(current_val, list) and key.isdigit():
    29	            idx = int(key)
    30	            if 0 <= idx < len(current_val):
    31	                current_val = current_val[idx]
    32	            else:
    33	                return default
    34	        elif isinstance(current_val, dict):
    35	            current_val = current_val.get(key)
    36	            if current_val is None:
    37	                return default
    38	        else:
    39	            return default
    40	    return current_val
    41	
    42	
    43	def parse_vote_count(vote_str: str) -> int:
    44	    """
    45	    Parses a vote count string (e.g., '1.2K', '25', '1M') into an integer.
    46	    """
    47	    if not isinstance(vote_str, str):
    48	        return 0
    49	    vote_str = vote_str.strip().upper()
    50	    if not vote_str:
    51	        return 0
    52	
    53	    if "K" in vote_str:
    54	        return int(float(vote_str.replace("K", "")) * 1_000)
    55	    elif "M" in vote_str:
    56	        return int(float(vote_str.replace("M", "")) * 1_000_000)
    57	    elif vote_str.isdigit():
    58	        return int(vote_str)
    59	    return 0
    60	
```

\`_deep_get()\` is the workhorse utility. YouTube's JSON structures are often 5-10 levels deep, so instead of chaining \`.get()\` calls, the codebase uses paths like \`"contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer"\`. It handles both dict keys and list indices (when the key segment is a digit).

\`parse_vote_count()\` handles YouTube's abbreviated number formats — turning "1.2K" into 1200, "1M" into 1000000, etc.

Now let's see the video ID extractor:

```bash
sed -n '62,99p' yt_meta/utils.py | cat -n
```

```output
     1	def extract_video_id(youtube_url: str) -> str:
     2	    """
     3	    Extract video ID from a YouTube URL.
     4	
     5	    Args:
     6	        youtube_url: YouTube video URL (can be regular or shorts URL) or just the video ID
     7	
     8	    Returns:
     9	        The video ID
    10	
    11	    Raises:
    12	        ValueError: If the video ID cannot be extracted
    13	    """
    14	    # If it's already just a video ID (11 characters, alphanumeric + _ and -)
    15	    if (
    16	        len(youtube_url) == 11
    17	        and youtube_url.replace("_", "").replace("-", "").isalnum()
    18	    ):
    19	        return youtube_url
    20	
    21	    # Handle regular URLs
    22	    if "v=" in youtube_url:
    23	        return youtube_url.split("v=")[1].split("&")[0]
    24	
    25	    # Handle shorts URLs
    26	    if "/shorts/" in youtube_url:
    27	        return youtube_url.split("/shorts/")[1].split("?")[0]
    28	
    29	    # Handle youtu.be URLs
    30	    if "youtu.be/" in youtube_url:
    31	        return youtube_url.split("youtu.be/")[1].split("?")[0]
    32	
    33	    # For testing purposes, allow any string that looks like it could be a video ID
    34	    # This includes test strings like "test_id", "invalid_id", etc.
    35	    if youtube_url and not youtube_url.startswith("http"):
    36	        return youtube_url
    37	
    38	    raise ValueError(f"Could not extract video ID from URL: {youtube_url}")
```

\`extract_video_id()\` handles every common YouTube URL format: standard \`watch?v=\` links, \`/shorts/\` URLs, \`youtu.be\` short links, and bare 11-character video IDs. It uses simple string splitting rather than regex — fast and readable.

## 5. Date Utilities (`date_utils.py`)

The date utility module converts relative date strings (like "1d", "2w", "3 months ago") into Python \`date\` objects. This is used by the filter system to let users specify date-based filters in human-friendly terms:

```bash
cat -n yt_meta/date_utils.py
```

```output
     1	# yt_meta/date_utils.py
     2	import re
     3	from datetime import date, datetime, timedelta
     4	
     5	
     6	def parse_relative_date_string(date_str: str) -> date:
     7	    """
     8	    Parses a relative date string into a date object.
     9	
    10	    Handles two main formats:
    11	    1. Shorthand notation (e.g., "1d", "2w", "3m", "4y" for days, weeks,
    12	       months, and years).
    13	    2. Human-readable notation (e.g., "1 day ago", "2 weeks ago").
    14	
    15	    Note:
    16	    - Months are approximated as 30 days.
    17	    - Years are approximated as 365 days.
    18	    - Returns today's date if the string format is unrecognized.
    19	    """
    20	    if not isinstance(date_str, str):
    21	        return datetime.today().date()
    22	
    23	    date_str = date_str.lower().strip()
    24	
    25	    # --- Handle Shorthand Notation (e.g., "1d", "2w", "3m", "4y") ---
    26	    shorthand_match = re.match(r"(\d+)\s*([dwmy])", date_str)
    27	    if shorthand_match:
    28	        value = int(shorthand_match.group(1))
    29	        unit = shorthand_match.group(2)
    30	
    31	        if unit == "d":
    32	            return datetime.today().date() - timedelta(days=value)
    33	        elif unit == "w":
    34	            return datetime.today().date() - timedelta(weeks=value)
    35	        elif unit == "m":
    36	            # Approximate months as 30 days
    37	            return datetime.today().date() - timedelta(days=value * 30)
    38	        elif unit == "y":
    39	            # Approximate years as 365 days
    40	            return datetime.today().date() - timedelta(days=value * 365)
    41	
    42	    # --- Handle Human-Readable Notation (e.g., "1 day ago", "2 weeks ago") ---
    43	    human_readable_match = re.match(r"(\d+)\s*(day|week|month|year)s?\s*ago", date_str)
    44	    if human_readable_match:
    45	        value = int(human_readable_match.group(1))
    46	        unit = human_readable_match.group(2)
    47	
    48	        if unit == "day":
    49	            return datetime.today().date() - timedelta(days=value)
    50	        elif unit == "week":
    51	            return datetime.today().date() - timedelta(weeks=value)
    52	        elif unit == "month":
    53	            return datetime.today().date() - timedelta(days=value * 30)
    54	        elif unit == "year":
    55	            return datetime.today().date() - timedelta(days=value * 365)
    56	
    57	    # Fallback for unrecognized formats
    58	    return datetime.today().date()
    59	
    60	
    61	parse_human_readable_date = parse_relative_date_string
```

Two regex patterns handle the two formats: shorthand (\`"1d"\`, \`"2w"\`) and human-readable (\`"1 day ago"\`, \`"2 weeks ago"\`). Months are approximated as 30 days and years as 365 days. The fallback returns today's date for unrecognized formats. The alias \`parse_human_readable_date\` at the bottom preserves backward compatibility.

## 6. Caching (`caching.py`)

The caching module provides two implementations behind a common interface: \`DummyCache\` (a no-op for when caching is disabled) and \`SQLiteCache\` (persistent, TTL-based caching using a local SQLite database). The fetchers accept a cache object, defaulting to \`DummyCache\`:

```bash
cat -n yt_meta/caching.py
```

```output
     1	import logging
     2	import pickle
     3	import sqlite3
     4	import time
     5	from collections.abc import MutableMapping
     6	from pathlib import Path
     7	
     8	logger = logging.getLogger(__name__)
     9	
    10	
    11	class DummyCache(MutableMapping):
    12	    """A dummy cache that stores nothing. Used when caching is disabled."""
    13	
    14	    def __getitem__(self, key):
    15	        raise KeyError(key)
    16	
    17	    def __setitem__(self, key, value):
    18	        pass
    19	
    20	    def __delitem__(self, key):
    21	        pass
    22	
    23	    def __iter__(self):
    24	        return iter([])
    25	
    26	    def __len__(self):
    27	        return 0
    28	
    29	
    30	class SQLiteCache(MutableMapping):
    31	    """
    32	    A cache that uses SQLite as a backend.
    33	    """
    34	
    35	    def __init__(self, path=".my_yt_meta_cache/cache.db", ttl_seconds=86400):
    36	        self.path = path
    37	        self.ttl_seconds = ttl_seconds
    38	        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
    39	        self._conn = sqlite3.connect(self.path)
    40	        self._conn.execute(
    41	            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value BLOB, timestamp REAL)"
    42	        )
    43	
    44	    def __enter__(self):
    45	        return self
    46	
    47	    def __exit__(self, exc_type, exc_val, exc_tb):
    48	        self._conn.close()
    49	
    50	    def __getitem__(self, key):
    51	        cursor = self._conn.execute(
    52	            "SELECT value, timestamp FROM cache WHERE key = ?", (key,)
    53	        )
    54	        result = cursor.fetchone()
    55	        if result is None:
    56	            raise KeyError(key)
    57	        value, timestamp = result
    58	        if timestamp < time.time() - self.ttl_seconds:
    59	            self.__delitem__(key)
    60	            raise KeyError(key)
    61	        return pickle.loads(value)
    62	
    63	    def __setitem__(self, key, value):
    64	        self._conn.execute(
    65	            "INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
    66	            (key, pickle.dumps(value), time.time()),
    67	        )
    68	        self._conn.commit()
    69	
    70	    def __delitem__(self, key):
    71	        self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
    72	        self._conn.commit()
    73	
    74	    def __iter__(self):
    75	        cursor = self._conn.execute("SELECT key FROM cache")
    76	        return (row[0] for row in cursor)
    77	
    78	    def __len__(self):
    79	        cursor = self._conn.execute("SELECT COUNT(*) FROM cache")
    80	        return cursor.fetchone()[0]
```

Both classes implement Python's \`MutableMapping\` ABC, so they work like dictionaries. \`DummyCache\` simply raises \`KeyError\` on every get and silently discards every set — a clean null-object pattern.

\`SQLiteCache\` stores serialized values (via \`pickle\`) in a SQLite table with timestamps. On read, it checks if the entry has expired based on \`ttl_seconds\` (default: 86400 = 24 hours). Expired entries are deleted on access. It also supports context-manager usage (\`with SQLiteCache() as cache:\`) for automatic connection cleanup.

## 7. Parsing (`parsing.py`)

This is the largest and most critical module — it handles extracting structured data from YouTube's HTML pages. YouTube embeds its page data as JSON blobs in \`<script>\` tags. The parser uses regex to find these blobs and then navigates the resulting JSON structures.

### 7a. JSON Extraction from HTML

The first section handles fetching pages and extracting embedded JSON:

```bash
sed -n '1,74p' yt_meta/parsing.py | cat -n
```

```output
     1	"""
     2	This module contains pure functions for parsing data from YouTube's HTML and JSON structures.
     3	"""
     4	
     5	import json
     6	import logging
     7	import re
     8	
     9	import dateparser
    10	
    11	from .exceptions import MetadataParsingError, VideoUnavailableError
    12	from .utils import _deep_get
    13	
    14	logger = logging.getLogger(__name__)
    15	
    16	# Regex patterns adopted from the parent youtube-comment-downloader library
    17	# for proven robustness.
    18	YT_CFG_RE = r"ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;"
    19	YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|(?:var\s+)?ytInitialData)\s*=\s*({.+?});'
    20	YT_INITIAL_PLAYER_RESPONSE_RE = r'(?:window\s*\[\s*["\']ytInitialPlayerResponse["\']\s*\]|(?:var\s+)?ytInitialPlayerResponse)\s*=\s*({.+?});'
    21	
    22	
    23	def _regex_search(text: str, pattern: str, default: str = "", flags: int = 0) -> str:
    24	    """Helper to run a regex search and return the first group or a default."""
    25	    match = re.search(pattern, text, flags)
    26	    return match.group(1) if match else default
    27	
    28	
    29	def find_ytcfg(html: str) -> dict | None:
    30	    """
    31	    Finds and parses the `ytcfg` data from a page's HTML source.
    32	
    33	    This data contains important context for making subsequent API requests,
    34	    such as the INNERTUBE_API_KEY and client version.
    35	    """
    36	    match = re.search(r"ytcfg\.set\s*\(\s*({.*?})\s*\)\s*;", html, re.DOTALL)
    37	    if match:
    38	        try:
    39	            return json.loads(match.group(1))
    40	        except json.JSONDecodeError:
    41	            logger.warning("Failed to parse ytcfg JSON.")
    42	            return None
    43	    logger.warning("Could not find ytcfg data in HTML.")
    44	    return None
    45	
    46	
    47	def extract_and_parse_json(html_content: str, variable_name: str) -> dict | None:
    48	    """
    49	    Extracts and parses a JSON object assigned to a JavaScript variable in HTML content.
    50	    """
    51	    # Use the proven, robust regex for the known complex YouTube variables.
    52	    if variable_name == "ytInitialData":
    53	        pattern = YT_INITIAL_DATA_RE
    54	    elif variable_name == "ytInitialPlayerResponse":
    55	        pattern = YT_INITIAL_PLAYER_RESPONSE_RE
    56	    else:
    57	        # Use a simpler, more generic pattern for other variables (e.g., in tests).
    58	        logger.warning(
    59	            f"Using generic regex for '{variable_name}'. This is less robust and intended for simple cases."
    60	        )
    61	        pattern = rf"var\s+{re.escape(variable_name)}\s*=\s*({{.*?}});"
    62	
    63	    json_str = _regex_search(html_content, pattern, flags=re.DOTALL)
    64	    if not json_str:
    65	        logger.warning(
    66	            f"Could not find JSON for '{variable_name}' using its designated regex."
    67	        )
    68	        return None
    69	
    70	    try:
    71	        return json.loads(json_str)
    72	    except json.JSONDecodeError as e:
    73	        logger.error(f"Failed to parse JSON for '{variable_name}': {e}")
    74	        return None
```

The three regex patterns at the top are the entry point for all scraping:
- **\`YT_INITIAL_DATA_RE\`** — matches the \`ytInitialData\` blob, which contains the video listing, channel info, and comment section structure.
- **\`YT_INITIAL_PLAYER_RESPONSE_RE\`** — matches the \`ytInitialPlayerResponse\` blob, which contains per-video metadata (title, view count, duration, etc.).
- **\`YT_CFG_RE\`** — matches the \`ytcfg.set()\` call, which contains the InnerTube API key and context needed for subsequent API calls (like fetching comments).

\`extract_and_parse_json()\` selects the right pattern by variable name, runs the regex, and returns the parsed JSON. This is the fundamental building block — every fetcher starts here.

### 7b. Video Renderer Parsing

Once we have the JSON blobs, we need to extract individual video entries. YouTube wraps each video in a "renderer" object. Here's how individual video renderers are parsed:

```bash
sed -n '376,424p' yt_meta/parsing.py | cat -n
```

```output
     1	def parse_video_renderer(renderer: dict) -> dict:
     2	    """
     3	    Parses a `videoRenderer` object into a simplified, flat dictionary.
     4	    """
     5	    if not renderer or not isinstance(renderer, dict):
     6	        return None
     7	
     8	    video_id = renderer.get("videoId")
     9	    if not video_id:
    10	        return None
    11	
    12	    badges = _deep_get(renderer, "badges", [])
    13	    is_live = any(
    14	        "LIVE" in b.get("metadataBadgeRenderer", {}).get("label", "") for b in badges
    15	    )
    16	    is_premiere = "PREMIERE" in _deep_get(
    17	        renderer, "upcomingEventData.upcomingEventText.runs.0.text", ""
    18	    )
    19	
    20	    view_count_text = _deep_get(renderer, "viewCountText.simpleText")
    21	    if not view_count_text:
    22	        # Sometimes it's in a different format
    23	        view_count_text = _deep_get(renderer, "viewCountText.runs.0.text")
    24	
    25	    channel_url_path = "longBylineText.runs.0.navigationEndpoint.commandMetadata.webCommandMetadata.url"
    26	    published_time_text = _deep_get(renderer, "publishedTimeText.simpleText")
    27	    publish_date = None
    28	    if published_time_text:
    29	        publish_date = dateparser.parse(
    30	            published_time_text, settings={"PREFER_DATES_FROM": "past"}
    31	        )
    32	
    33	    return {
    34	        "video_id": video_id,
    35	        "title": _deep_get(renderer, "title.runs.0.text"),
    36	        "description_snippet": _deep_get(renderer, "descriptionSnippet.runs.0.text"),
    37	        "thumbnails": _deep_get(renderer, "thumbnail.thumbnails", []),
    38	        "channel_name": _deep_get(renderer, "longBylineText.runs.0.text"),
    39	        "channel_url": _deep_get(renderer, channel_url_path),
    40	        "duration_seconds": parse_duration(
    41	            _deep_get(renderer, "lengthText.accessibility.accessibilityData.label")
    42	        ),
    43	        "view_count": parse_view_count(view_count_text),
    44	        "publish_date": publish_date,
    45	        "published_time_text": published_time_text,
    46	        "is_live": is_live,
    47	        "is_premiere": is_premiere,
    48	        "url": f"https://www.youtube.com/watch?v={video_id}",
    49	    }
```

\`parse_video_renderer()\` transforms YouTube's nested renderer objects into flat, usable dictionaries. Notice the heavy use of \`_deep_get()\` to safely traverse paths like \`"longBylineText.runs.0.navigationEndpoint.commandMetadata.webCommandMetadata.url"\`. It also detects live streams and premieres by checking badge metadata. Publish dates are parsed using the \`dateparser\` library for flexible date string handling.

### 7c. Full Video Metadata Parsing

For single-video pages, we also parse the \`ytInitialPlayerResponse\` which contains richer metadata (full description, category, keywords, like counts):

```bash
sed -n '502,539p' yt_meta/parsing.py | cat -n
```

```output
     1	def parse_video_metadata(player_response_data: dict, initial_data: dict) -> dict:
     2	    """
     3	    Parses comprehensive video metadata from the `ytInitialPlayerResponse`
     4	    and `ytInitialData` objects from a video's watch page.
     5	    """
     6	    if not player_response_data and not initial_data:
     7	        logger.error("Could not extract playerResponse or initialData from page.")
     8	        raise VideoUnavailableError(
     9	            "Could not extract playerResponse or initialData from page."
    10	        )
    11	
    12	    video_details = _deep_get(player_response_data, "videoDetails", {})
    13	    microformat = _deep_get(
    14	        player_response_data, "microformat.playerMicroformatRenderer", {}
    15	    )
    16	
    17	    subscriber_path = (
    18	        "contents.twoColumnWatchNextResults.results.results.contents.1"
    19	        ".videoSecondaryInfoRenderer.owner.videoOwnerRenderer.subscriberCountText.simpleText"
    20	    )
    21	    return {
    22	        "video_id": video_details.get("videoId"),
    23	        "title": video_details.get("title"),
    24	        "channel_name": video_details.get("author"),
    25	        "channel_id": video_details.get("channelId"),
    26	        "duration_seconds": int(video_details.get("lengthSeconds", 0)),
    27	        "view_count": int(video_details.get("viewCount", 0)),
    28	        "publish_date": microformat.get("publishDate"),
    29	        "upload_date": microformat.get("uploadDate"),
    30	        "category": microformat.get("category"),
    31	        "like_count": find_like_count(player_response_data),
    32	        "keywords": video_details.get("keywords", []),
    33	        "thumbnails": _deep_get(video_details, "thumbnail.thumbnails", []),
    34	        "is_live": video_details.get("isLiveContent", False),
    35	        "full_description": video_details.get("shortDescription"),
    36	        "heatmap": find_heatmap(initial_data),
    37	        "subscriber_count_text": _deep_get(initial_data, subscriber_path),
    38	    }
```

\`parse_video_metadata()\` combines data from two JSON sources: \`ytInitialPlayerResponse\` (for video details like duration, view count, keywords) and \`ytInitialData\` (for subscriber count, heatmap data). The result is a comprehensive metadata dictionary that includes everything from basic info to engagement metrics and even the video's engagement heatmap.

## 8. Filter Validation (`validators.py`)

Before filters are applied, they must be validated. The \`validators\` module defines a schema for every filterable field and checks that user-provided filters use valid operators and value types:

```bash
cat -n yt_meta/validators.py
```

```output
     1	from datetime import date, datetime
     2	
     3	NUMERIC_OPERATORS = {"gt", "gte", "lt", "lte", "eq"}
     4	TEXT_OPERATORS = {"contains", "re", "eq"}
     5	LIST_OPERATORS = {"contains_any", "contains_all"}
     6	BOOL_OPERATORS = {"eq"}
     7	
     8	FILTER_SCHEMA = {
     9	    # Video/Shorts Filters
    10	    "view_count": {
    11	        "type": int,
    12	        "operators": NUMERIC_OPERATORS,
    13	        "schema_type": "numerical",
    14	    },
    15	    "duration_seconds": {
    16	        "type": int,
    17	        "operators": NUMERIC_OPERATORS,
    18	        "schema_type": "numerical",
    19	    },
    20	    "like_count": {
    21	        "type": int,
    22	        "operators": NUMERIC_OPERATORS,
    23	        "schema_type": "numerical",
    24	    },
    25	    "title": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    26	    "description_snippet": {
    27	        "type": str,
    28	        "operators": TEXT_OPERATORS,
    29	        "schema_type": "text",
    30	    },
    31	    "full_description": {
    32	        "type": str,
    33	        "operators": TEXT_OPERATORS,
    34	        "schema_type": "text",
    35	    },
    36	    "category": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    37	    "keywords": {"type": list, "operators": LIST_OPERATORS, "schema_type": "list"},
    38	    "publish_date": {
    39	        "type": (str, date, datetime),
    40	        "operators": NUMERIC_OPERATORS,
    41	        "schema_type": "date",
    42	    },
    43	    # Comment Filters
    44	    "reply_count": {
    45	        "type": int,
    46	        "operators": NUMERIC_OPERATORS,
    47	        "schema_type": "numerical",
    48	    },
    49	    "author": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    50	    "text": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    51	    "channel_id": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    52	    "is_reply": {"type": bool, "operators": BOOL_OPERATORS, "schema_type": "bool"},
    53	    "is_hearted_by_owner": {
    54	        "type": bool,
    55	        "operators": BOOL_OPERATORS,
    56	        "schema_type": "bool",
    57	    },
    58	    "is_by_owner": {"type": bool, "operators": BOOL_OPERATORS, "schema_type": "bool"},
    59	}
    60	
    61	
    62	def validate_filters(filters: dict):
    63	    """
    64	    Validates a filter dictionary against the defined FILTER_SCHEMA.
    65	
    66	    Raises:
    67	        ValueError: If a filter field or operator is invalid.
    68	        TypeError: If a filter value has an incorrect type.
    69	    """
    70	    if not filters:
    71	        return
    72	
    73	    for field, conditions in filters.items():
    74	        if field not in FILTER_SCHEMA:
    75	            raise ValueError(f"Unknown filter field: '{field}'")
    76	
    77	        schema = FILTER_SCHEMA[field]
    78	        valid_operators = schema["operators"]
    79	
    80	        if not isinstance(conditions, dict):
    81	            raise TypeError(f"Filter for '{field}' must be a dictionary.")
    82	
    83	        for op, value in conditions.items():
    84	            if op not in valid_operators:
    85	                raise ValueError(f"Invalid operator '{op}' for field '{field}'")
    86	
    87	            # Type check the value
    88	            value_type_valid = False
    89	            if field == "publish_date":
    90	                if isinstance(value, str | date | datetime):
    91	                    value_type_valid = True
    92	            elif op in TEXT_OPERATORS and isinstance(value, str):
    93	                value_type_valid = True
    94	            elif op in NUMERIC_OPERATORS and isinstance(value, int | float):
    95	                value_type_valid = True
    96	            elif op in LIST_OPERATORS and isinstance(value, list):
    97	                value_type_valid = True
    98	            elif op in BOOL_OPERATORS and isinstance(value, bool):
    99	                value_type_valid = True
   100	
   101	            if not value_type_valid:
   102	                raise TypeError(
   103	                    f"Invalid value type for '{field}' filter. "
   104	                    f"Expected {schema['type']}, got {type(value)}"
   105	                )
```

The schema is a declarative dictionary mapping field names to their allowed types, operators, and schema categories. There are four operator families:
- **Numeric** (\`gt\`, \`gte\`, \`lt\`, \`lte\`, \`eq\`): for view_count, duration_seconds, like_count, reply_count, and publish_date
- **Text** (\`contains\`, \`re\`, \`eq\`): for title, description, author, etc.
- **List** (\`contains_any\`, \`contains_all\`): for keywords
- **Bool** (\`eq\`): for is_reply, is_hearted_by_owner, is_by_owner

\`validate_filters()\` checks each filter dict entry against this schema — wrong field names, invalid operators, or mistyped values all raise descriptive errors before any fetching begins.

## 9. Filtering Engine (`filtering.py`)

This module implements the actual filter application logic. It has a clever two-stage design: "fast" filters (numeric, text, date, bool) can be evaluated on partial data from channel listings, while "slow" filters (like \`full_description\`, \`like_count\`, \`category\`, \`keywords\`) require fetching each video's individual page. The \`partition_filters()\` function splits user filters into these two buckets:

```bash
sed -n '1,77p' yt_meta/filtering.py | cat -n
```

```output
     1	"""
     2	This module contains the logic for advanced, dictionary-based filtering.
     3	
     4	It defines which filters are "fast" (available on the initial page load) and
     5	which are "slow" (requiring a separate request per video). The main entry
     6	point is `apply_filters`, which checks if a given video dictionary meets a
     7	set of specified criteria.
     8	"""
     9	
    10	import logging
    11	import re
    12	from datetime import date, datetime
    13	
    14	import dateparser
    15	
    16	from yt_meta.validators import FILTER_SCHEMA
    17	
    18	logger = logging.getLogger(__name__)
    19	
    20	
    21	# These keys are available in the basic video metadata from channel/playlist pages.
    22	FAST_VIDEO_FILTERS = {
    23	    "view_count",
    24	    "duration_seconds",
    25	    "publish_date",
    26	    "title",
    27	    "description_snippet",
    28	}
    29	FAST_SHORTS_FILTERS = {"view_count", "title"}
    30	
    31	# These keys require fetching full metadata for each video, making them slower.
    32	SLOW_FILTER_KEYS = {
    33	    "like_count",
    34	    "category",
    35	    "keywords",
    36	    "full_description",
    37	}
    38	
    39	COMMENT_FILTER_KEYS = {
    40	    "text",
    41	    "author",
    42	    "like_count",
    43	    "reply_count",
    44	    "publish_date",
    45	    "is_reply",
    46	    "is_hearted_by_owner",
    47	    "is_by_owner",
    48	    "channel_id",
    49	}
    50	
    51	
    52	def partition_filters(filters: dict, content_type: str) -> tuple[dict, dict]:
    53	    """
    54	    Partitions filters into fast and slow filters based on the content type.
    55	
    56	    Fast filters can be applied to the basic metadata fetched in the initial channel/shorts page load.
    57	    Slow filters require fetching full metadata for each individual video/short.
    58	
    59	    Args:
    60	        filters: The dictionary of filter conditions.
    61	        content_type: The type of content, either 'videos' or 'shorts'.
    62	
    63	    Returns:
    64	        A tuple of (fast_filters, slow_filters).
    65	    """
    66	    if not filters:
    67	        return {}, {}
    68	    fast_filters = {}
    69	    slow_filters = {}
    70	    for key, value in filters.items():
    71	        if content_type == "videos" and key in FAST_VIDEO_FILTERS:
    72	            fast_filters[key] = value
    73	        elif content_type == "shorts" and key in FAST_SHORTS_FILTERS:
    74	            fast_filters[key] = value
    75	        else:
    76	            slow_filters[key] = value
    77	    return fast_filters, slow_filters
```

The partition is performance-critical: fast filters eliminate videos using data already available from the channel page listing (view count, duration, title, publish date), avoiding expensive per-video HTTP requests. Slow filters (like_count, category, keywords, full_description) require fetching each video's individual watch page, so they're applied in a second pass only on videos that survived fast filtering.

Now let's see the core \`apply_filters()\` function that evaluates a video against filter criteria:

```bash
sed -n '193,232p' yt_meta/filtering.py | cat -n
```

```output
     1	def apply_filters(video: dict, filters: dict | None) -> bool:
     2	    """
     3	    Checks if a video dictionary passes a set of filters.
     4	
     5	    Args:
     6	        video: The video metadata dictionary.
     7	        filters: The dictionary of filters to apply.
     8	
     9	    Returns:
    10	        True if the video passes all filters, False otherwise.
    11	    """
    12	    if filters is None:
    13	        return True  # If no filters are provided, consider the video as passing
    14	
    15	    for key, condition in filters.items():
    16	        if video.get(key) is None:
    17	            return False  # If the key doesn't exist, it can't match
    18	
    19	        schema_type = FILTER_SCHEMA[key]["schema_type"]
    20	        video_value = video.get(key)
    21	
    22	        passes = True  # Assume true and break on first failure
    23	        if schema_type == "numerical":
    24	            passes = _check_numerical_condition(video_value, condition)
    25	        elif schema_type == "date":
    26	            for op, condition_value in condition.items():
    27	                if not _check_date_condition(video_value, condition_value, op):
    28	                    passes = False
    29	                    break
    30	        elif schema_type == "text":
    31	            passes = _check_text_condition(video_value, condition)
    32	        elif schema_type == "list":
    33	            passes = _check_list_condition(video_value, condition)
    34	        elif schema_type == "bool":
    35	            passes = _check_boolean_condition(video_value, condition)
    36	
    37	        if not passes:
    38	            return False
    39	
    40	    return True
```

\`apply_filters()\` is the gatekeeper: it iterates over all filter conditions, dispatches to type-specific checkers (\`_check_numerical_condition\`, \`_check_date_condition\`, \`_check_text_condition\`, \`_check_list_condition\`, \`_check_boolean_condition\`), and short-circuits on the first failure. Videos with missing keys for any filter field are automatically rejected.

## 10. Fetchers (`fetchers.py`)

The fetcher module contains the three main data-retrieval classes: \`VideoFetcher\`, \`ChannelFetcher\`, and \`PlaylistFetcher\`. They all inherit from \`_BaseFetcher\`, which provides the two-stage filter pipeline.

### 10a. _BaseFetcher — The Two-Stage Filter Pipeline

The base class implements the generator that applies fast filters immediately and slow filters lazily:

```bash
sed -n '34,87p' yt_meta/fetchers.py | cat -n
```

```output
     1	    def _process_videos_generator(
     2	        self,
     3	        video_generator,
     4	        must_fetch_full_metadata,
     5	        fast_filters,
     6	        slow_filters,
     7	        stop_at_video_id,
     8	        max_videos,
     9	    ):
    10	        videos_processed = 0
    11	        for video in video_generator:
    12	            if not apply_filters(video, fast_filters):
    13	                continue
    14	            merged_video = video
    15	            if must_fetch_full_metadata:
    16	                try:
    17	                    video_url = f"https://www.youtube.com/watch?v={video['video_id']}"
    18	                    full_meta = self.video_fetcher.get_video_metadata(video_url)
    19	                    if full_meta:
    20	                        merged_video = {**video, **full_meta}
    21	                    else:
    22	                        if slow_filters:
    23	                            continue
    24	                except (VideoUnavailableError, MetadataParsingError) as e:
    25	                    self.logger.error(
    26	                        "Error fetching metadata for video_id %s: %s",
    27	                        video["video_id"],
    28	                        e,
    29	                    )
    30	                    continue
    31	            if not apply_filters(merged_video, slow_filters):
    32	                continue
    33	            yield merged_video
    34	            videos_processed += 1
    35	            if stop_at_video_id and video["video_id"] == stop_at_video_id:
    36	                return
    37	            if max_videos != -1 and videos_processed >= max_videos:
    38	                return
    39	
    40	    def _get_continuation_data(self, token: str, ytcfg: dict):
    41	        cache_key = f"continuation:{token}"
    42	        if cache_key in self.cache:
    43	            self.logger.info(f"Cache hit for continuation token: {token[:10]}...")
    44	            return self.cache[cache_key]
    45	        data = {"context": ytcfg["INNERTUBE_CONTEXT"], "continuation": token}
    46	        response = self.session.post(
    47	            f"https://www.youtube.com/youtubei/v1/browse?key={ytcfg['INNERTUBE_API_KEY']}",
    48	            json=data,
    49	            timeout=10,
    50	        )
    51	        response.raise_for_status()
    52	        result = response.json()
    53	        self.cache[cache_key] = result
    54	        return result
```

The two-stage pipeline in \`_process_videos_generator()\`:
1. **Fast filter pass** (line 12): Each video from the raw generator is immediately tested against fast filters. Failures are skipped without any extra HTTP requests.
2. **Full metadata fetch** (lines 15-30): Only if slow filters exist (or full metadata was explicitly requested), the fetcher makes a per-video HTTP request to get complete metadata and merges it with the partial data.
3. **Slow filter pass** (line 31): The enriched video dict is tested against slow filters.
4. **Yield** (line 33): Only videos surviving both passes are yielded to the caller.

\`_get_continuation_data()\` handles pagination — YouTube uses "continuation tokens" to load subsequent pages. This method POSTs to YouTube's InnerTube browse API with the token and caches results.

### 10b. VideoFetcher — Single Video Metadata

```bash
sed -n '90,138p' yt_meta/fetchers.py | cat -n
```

```output
     1	class VideoFetcher:
     2	    """Fetches data related to a single YouTube video."""
     3	
     4	    def __init__(self, session: httpx.Client, cache: MutableMapping | None):
     5	        self.session = session
     6	        self.cache = cache
     7	
     8	    def get_video_metadata(self, youtube_url: str) -> dict:
     9	        """
    10	        Fetches and parses comprehensive metadata for a given YouTube video.
    11	
    12	        Args:
    13	            youtube_url: The full URL of the YouTube video.
    14	
    15	        Returns:
    16	            A dictionary containing detailed video metadata.
    17	        """
    18	        logger.info(f"Fetching video page: {youtube_url}")
    19	        video_id = youtube_url.split("v=")[-1]
    20	        cache_key = f"video_meta:{video_id}"
    21	        if cache_key in self.cache:
    22	            logger.info(f"Cache hit for video metadata: {video_id}")
    23	            return self.cache[cache_key]
    24	
    25	        try:
    26	            response = self.session.get(youtube_url, timeout=10)
    27	            response.raise_for_status()
    28	            html = response.text
    29	        except httpx.RequestError as e:
    30	            logger.error(f"Failed to fetch video page {youtube_url}: {e}")
    31	            raise VideoUnavailableError(
    32	                f"Failed to fetch video page: {e}", video_id=youtube_url.split("v=")[-1]
    33	            ) from e
    34	
    35	        player_response_data = parsing.extract_and_parse_json(
    36	            html, "ytInitialPlayerResponse"
    37	        )
    38	        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
    39	
    40	        if not player_response_data or not initial_data:
    41	            logger.warning(
    42	                f"Could not extract metadata for video {video_id}. "
    43	                "The page structure may have changed or the video is unavailable. Skipping."
    44	            )
    45	            return None
    46	
    47	        result = parsing.parse_video_metadata(player_response_data, initial_data)
    48	        self.cache[cache_key] = result
    49	        return result
```

\`VideoFetcher.get_video_metadata()\` is the simplest fetcher: it GETs a watch page, extracts both JSON blobs (\`ytInitialPlayerResponse\` and \`ytInitialData\`) via the parsing module, and returns the merged metadata dictionary. Results are cached by video ID.

### 10c. ChannelFetcher — Paginated Channel Video Listing

The \`ChannelFetcher\` handles the more complex task of iterating through all videos on a channel, including pagination:

```bash
sed -n '391,459p' yt_meta/fetchers.py | cat -n
```

```output
     1	    def get_channel_videos(
     2	        self,
     3	        channel_url,
     4	        force_refresh=False,
     5	        fetch_full_metadata=False,
     6	        start_date=None,
     7	        end_date=None,
     8	        filters=None,
     9	        stop_at_video_id=None,
    10	        max_videos=-1,
    11	    ):
    12	        """
    13	        Fetches videos from a YouTube channel's videos and shorts tab.
    14	
    15	        Args:
    16	            channel_url: The URL of the channel's videos page.
    17	            force_refresh: Whether to bypass the cache and fetch fresh data.
    18	            fetch_full_metadata: Whether to fetch full metadata for each video.
    19	            start_date: The start date for filtering videos.
    20	            end_date: The end date for filtering videos.
    21	            filters: A dictionary of filter conditions.
    22	            stop_at_video_id: The ID of the video to stop fetching at.
    23	            max_videos: The maximum number of videos to fetch (-1 for all).
    24	
    25	        Returns:
    26	            A generator of video dictionaries.
    27	        """
    28	        validate_filters(filters)
    29	        if not channel_url.endswith("/videos"):
    30	            channel_url = f"{channel_url.rstrip('/')}/videos"
    31	        if filters is None:
    32	            filters = {}
    33	        publish_date_from_filter = filters.get("publish_date", {})
    34	        start_date_from_filter = publish_date_from_filter.get(
    35	            "gt"
    36	        ) or publish_date_from_filter.get("gte")
    37	        end_date_from_filter = publish_date_from_filter.get(
    38	            "lt"
    39	        ) or publish_date_from_filter.get("lte")
    40	        final_start_date = start_date or start_date_from_filter
    41	        final_end_date = end_date or end_date_from_filter
    42	        if isinstance(final_start_date, str):
    43	            final_start_date = parse_relative_date_string(final_start_date)
    44	        if isinstance(final_end_date, str):
    45	            final_end_date = parse_relative_date_string(final_end_date)
    46	        date_filter_conditions = {}
    47	        if final_start_date:
    48	            date_filter_conditions["gte"] = final_start_date
    49	        if final_end_date:
    50	            date_filter_conditions["lte"] = final_end_date
    51	        if date_filter_conditions:
    52	            filters["publish_date"] = date_filter_conditions
    53	        fast_filters, slow_filters = partition_filters(filters, content_type="videos")
    54	        must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)
    55	        if slow_filters and not fetch_full_metadata:
    56	            self.logger.warning(
    57	                f"Slow filters {list(slow_filters.keys())} provided without fetch_full_metadata=True. Full metadata will be fetched."
    58	            )
    59	        raw_video_generator = self._get_raw_channel_videos_generator(
    60	            channel_url, force_refresh, final_start_date
    61	        )
    62	        yield from self._process_videos_generator(
    63	            video_generator=raw_video_generator,
    64	            must_fetch_full_metadata=must_fetch_full_metadata,
    65	            fast_filters=fast_filters,
    66	            slow_filters=slow_filters,
    67	            stop_at_video_id=stop_at_video_id,
    68	            max_videos=max_videos,
    69	        )
```

\`get_channel_videos()\` orchestrates the entire flow:
1. **Validates filters** up front (line 28)
2. **Resolves date filters** — merging explicit \`start_date\`/\`end_date\` params with any \`publish_date\` filter conditions, converting relative date strings via \`parse_relative_date_string()\` (lines 33-52)
3. **Partitions filters** into fast and slow buckets (line 53)
4. **Auto-detects** whether full metadata fetching is needed based on slow filter presence (line 54)
5. **Creates the raw generator** for the initial channel page listing (line 59)
6. **Delegates to the two-stage pipeline** inherited from \`_BaseFetcher\` (line 62)

This method returns a generator, so videos are yielded lazily — the caller controls how many to consume.

### 10d. PlaylistFetcher

The \`PlaylistFetcher\` works similarly but navigates playlist-specific JSON structures:

```bash
sed -n '517,562p' yt_meta/fetchers.py | cat -n
```

```output
     1	    def _get_raw_playlist_videos_generator(self, playlist_id: str):
     2	        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
     3	        try:
     4	            response = self.session.get(playlist_url, timeout=10)
     5	            response.raise_for_status()
     6	            html = response.text
     7	        except httpx.RequestError as e:
     8	            raise VideoUnavailableError(
     9	                f"Could not fetch playlist page: {e}", playlist_id=playlist_id
    10	            ) from e
    11	        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
    12	        if not initial_data:
    13	            raise MetadataParsingError(
    14	                "Could not extract ytInitialData from playlist page.",
    15	                playlist_id=playlist_id,
    16	            )
    17	        ytcfg = parsing.find_ytcfg(html)
    18	        if not ytcfg:
    19	            raise MetadataParsingError(
    20	                "Could not extract ytcfg from playlist page.", playlist_id=playlist_id
    21	            )
    22	        path = "contents.twoColumnBrowseResultsRenderer.tabs.0.tabRenderer.content.sectionListRenderer.contents.0.itemSectionRenderer.contents.0.playlistVideoListRenderer"
    23	        renderer = _deep_get(initial_data, path)
    24	        if not renderer:
    25	            self.logger.warning(
    26	                "No video renderers found on the initial playlist page: %s", playlist_id
    27	            )
    28	            return
    29	        videos, continuation_token = parsing.extract_videos_from_playlist_renderer(
    30	            renderer
    31	        )
    32	        while True:
    33	            yield from videos
    34	            if not continuation_token:
    35	                break
    36	            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
    37	            if not continuation_data:
    38	                break
    39	            renderers = _deep_get(
    40	                continuation_data,
    41	                "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems",
    42	                [],
    43	            )
    44	            videos, continuation_token = parsing.extract_videos_from_playlist_renderer(
    45	                {"contents": renderers}
    46	            )
```

The playlist fetcher follows the same pattern as the channel fetcher:
1. Fetch the playlist page HTML
2. Extract \`ytInitialData\` and \`ytcfg\`
3. Navigate to the playlist video list renderer using a deep path (line 22)
4. Extract videos and a continuation token from the renderer
5. Loop: yield the current batch, then fetch the next page using the continuation token via the InnerTube API

Note the long path on line 22 — this is a concrete example of why \`_deep_get()\` exists. Without it, you'd need 7+ levels of nested \`.get()\` calls.

## 11. Comment System

The comment system has a three-layer architecture:
- **\`CommentAPIClient\`** — makes the raw HTTP requests to YouTube's InnerTube API
- **\`CommentParser\`** — extracts structured comment data from the API responses
- **\`CommentFetcher\`** — orchestrates the pagination loop, combining the client and parser

### 11a. CommentAPIClient (`comment_api_client.py`)

The API client handles the low-level details of YouTube's comment API: fetching the initial page data, finding sort endpoints (top comments vs. newest first), and making continuation requests:

```bash
sed -n '44,171p' yt_meta/comment_api_client.py | cat -n
```

```output
     1	    def get_initial_video_data(self, video_id: str) -> tuple[dict, dict]:
     2	        """Get initial video page data and ytcfg."""
     3	        url = f"https://www.youtube.com/watch?v={video_id}"
     4	
     5	        try:
     6	            response = self.client.get(url)
     7	            response.raise_for_status()
     8	            html_content = response.text
     9	
    10	            ytcfg = self._extract_ytcfg(html_content)
    11	            initial_data = self._extract_initial_data(html_content)
    12	
    13	            return initial_data, ytcfg
    14	
    15	        except Exception as e:
    16	            raise VideoUnavailableError(f"Could not load video page: {e}") from e
    17	
    18	    def _extract_ytcfg(self, html_content: str) -> dict:
    19	        """Extract ytcfg configuration from HTML."""
    20	        ytcfg_pattern = r"ytcfg\.set\s*\(\s*({.+?})\s*\)"
    21	        match = re.search(ytcfg_pattern, html_content, re.DOTALL)
    22	
    23	        if match:
    24	            try:
    25	                return json.loads(match.group(1))
    26	            except json.JSONDecodeError:
    27	                pass
    28	
    29	        return {}
    30	
    31	    def _extract_initial_data(self, html_content: str) -> dict:
    32	        """Extract ytInitialData from HTML."""
    33	        initial_data_pattern = r"var\s+ytInitialData\s*=\s*({.+?});"
    34	        match = re.search(initial_data_pattern, html_content, re.DOTALL)
    35	
    36	        if match:
    37	            try:
    38	                return json.loads(match.group(1))
    39	            except json.JSONDecodeError:
    40	                pass
    41	
    42	        return {}
    43	
    44	    def get_sort_endpoints_flexible(
    45	        self, initial_data: dict, ytcfg: dict
    46	    ) -> dict[str, str]:
    47	        """
    48	        Flexibly detect comment sort endpoints from various locations in the YouTube response.
    49	        This method searches multiple places for comment sorting options to be resilient
    50	        to YouTube's changing structure.
    51	        """
    52	        endpoints = {}
    53	
    54	        def find_sort_filter_menus(obj, path=""):
    55	            """Recursively search for sortFilterSubMenuRenderer anywhere in the data."""
    56	            if isinstance(obj, dict):
    57	                if "sortFilterSubMenuRenderer" in obj:
    58	                    submenu = obj["sortFilterSubMenuRenderer"]
    59	                    if "subMenuItems" in submenu:
    60	                        logger.debug(f"Found sortFilterSubMenuRenderer at path: {path}")
    61	                        for item in submenu["subMenuItems"]:
    62	                            title = item.get("title", "").lower()
    63	                            endpoint = (
    64	                                item.get("serviceEndpoint", {})
    65	                                .get("continuationCommand", {})
    66	                                .get("token")
    67	                            )
    68	                            if endpoint:
    69	                                endpoints[title] = endpoint
    70	                                logger.debug(
    71	                                    f"Added endpoint: {title} -> {endpoint[:50]}..."
    72	                                )
    73	
    74	                for key, value in obj.items():
    75	                    find_sort_filter_menus(value, f"{path}.{key}" if path else key)
    76	            elif isinstance(obj, list):
    77	                for i, item in enumerate(obj):
    78	                    find_sort_filter_menus(item, f"{path}[{i}]" if path else f"[{i}]")
    79	
    80	        def find_engagement_panels(obj):
    81	            """Look for engagement panels that might contain comment endpoints."""
    82	            if isinstance(obj, dict):
    83	                if "engagementPanels" in obj:
    84	                    panels = obj["engagementPanels"]
    85	                    for panel in panels:
    86	                        if self._is_comment_panel(panel):
    87	                            self._extract_endpoints_from_panel(panel, endpoints)
    88	
    89	                for value in obj.values():
    90	                    find_engagement_panels(value)
    91	            elif isinstance(obj, list):
    92	                for item in obj:
    93	                    find_engagement_panels(item)
    94	
    95	        def find_continuation_tokens(obj):
    96	            """Look for continuation tokens that might be comment-related."""
    97	            if isinstance(obj, dict):
    98	                for key, value in obj.items():
    99	                    if "token" in key.lower() and isinstance(value, str):
   100	                        if self._is_comment_token(value):
   101	                            # Try to determine if this is top or recent based on context
   102	                            context_key = key.lower()
   103	                            if "top" in context_key or "best" in context_key:
   104	                                endpoints["top comments"] = value
   105	                            elif "new" in context_key or "recent" in context_key:
   106	                                endpoints["newest first"] = value
   107	                            else:
   108	                                endpoints[f"comments_{len(endpoints)}"] = value
   109	
   110	                for value in obj.values():
   111	                    find_continuation_tokens(value)
   112	            elif isinstance(obj, list):
   113	                for item in obj:
   114	                    find_continuation_tokens(item)
   115	
   116	        # Search strategies in order of preference
   117	        find_sort_filter_menus(initial_data)
   118	
   119	        if not endpoints:
   120	            find_engagement_panels(initial_data)
   121	
   122	        if not endpoints:
   123	            find_continuation_tokens(initial_data)
   124	
   125	        logger.info(
   126	            f"Found {len(endpoints)} comment endpoints: {list(endpoints.keys())}"
   127	        )
   128	        return endpoints
```

\`get_initial_video_data()\` fetches the watch page and extracts both \`ytcfg\` (API credentials) and \`ytInitialData\` (page structure). These are passed to \`get_sort_endpoints_flexible()\`, which uses three cascading search strategies to find comment sort tokens:

1. **\`find_sort_filter_menus()\`** — recursively searches the JSON for \`sortFilterSubMenuRenderer\` nodes that contain "Top comments" and "Newest first" tokens
2. **\`find_engagement_panels()\`** — looks for comment panels in the engagement panel section
3. **\`find_continuation_tokens()\`** — last resort, finds any comment-related continuation tokens

This layered approach makes the client resilient to YouTube's frequently changing data structure.

### 11b. CommentParser (`comment_parser.py`)

The parser extracts structured comment data from the API responses. It handles both the legacy \`commentRenderer\` format and the newer entity-based format:

```bash
sed -n '459,551p' yt_meta/comment_parser.py | cat -n
```

```output
     1	    def extract_complete_comments(self, api_response: dict) -> list[dict[str, Any]]:
     2	        """
     3	        Extract complete comment data directly from commentEntityPayload.
     4	        This approach gets all data (comment, author, toolbar) from a single payload.
     5	
     6	        Args:
     7	            api_response: API response data
     8	
     9	        Returns:
    10	            List of complete comment dictionaries
    11	        """
    12	        comments = []
    13	
    14	        def search_complete_comments(obj):
    15	            if isinstance(obj, dict):
    16	                if "commentEntityPayload" in obj:
    17	                    payload = obj["commentEntityPayload"]
    18	
    19	                    # Extract comment properties
    20	                    properties = payload.get("properties", {})
    21	                    comment_id = properties.get("commentId")
    22	
    23	                    if not comment_id:
    24	                        return
    25	
    26	                    # Extract text content
    27	                    content = properties.get("content", {})
    28	                    text = content.get("content", "")
    29	
    30	                    # Extract author data directly from payload
    31	                    author_data = payload.get("author", {})
    32	                    author_name = author_data.get("displayName", "Unknown")
    33	                    author_channel_id = author_data.get("channelId", "")
    34	                    author_avatar_url = author_data.get("avatarThumbnailUrl", "")
    35	                    is_verified = author_data.get("isVerified", False)
    36	                    is_creator = author_data.get("isCreator", False)
    37	
    38	                    # Extract toolbar data directly from payload
    39	                    toolbar_data = payload.get("toolbar", {})
    40	                    like_count = self._parse_engagement_count(
    41	                        toolbar_data.get("likeCountNotliked")
    42	                        or toolbar_data.get("likeCountLiked")
    43	                        or "0"
    44	                    )
    45	                    reply_count = self._parse_engagement_count(
    46	                        toolbar_data.get("replyCount", "0")
    47	                    )
    48	
    49	                    # Extract time information
    50	                    published_time = properties.get("publishedTime", "")
    51	                    publish_date = None
    52	                    if published_time:
    53	                        try:
    54	                            publish_date = parse_relative_date_string(published_time)
    55	                        except Exception:
    56	                            pass
    57	
    58	                    # Extract other properties
    59	                    reply_level = properties.get("replyLevel", 0)
    60	                    is_reply = reply_level > 0
    61	
    62	                    comment = {
    63	                        "id": comment_id,
    64	                        "text": text,
    65	                        "author": author_name,
    66	                        "author_channel_id": author_channel_id,
    67	                        "author_avatar_url": author_avatar_url,
    68	                        "publish_date": publish_date,
    69	                        "time_human": published_time,
    70	                        "time_parsed": None,
    71	                        "like_count": like_count,
    72	                        "reply_count": reply_count,
    73	                        "is_hearted": False,  # Can be extracted from toolbar states if needed
    74	                        "is_reply": is_reply,
    75	                        "is_pinned": False,  # Can be determined from other data if needed
    76	                        "paid_comment": None,
    77	                        "author_badges": [],  # Can be extracted from author data if needed
    78	                        "parent_id": None,  # For replies
    79	                        "is_verified": is_verified,
    80	                        "is_creator": is_creator,
    81	                    }
    82	
    83	                    comments.append(comment)
    84	
    85	                for value in obj.values():
    86	                    search_complete_comments(value)
    87	            elif isinstance(obj, list):
    88	                for item in obj:
    89	                    search_complete_comments(item)
    90	
    91	        search_complete_comments(api_response)
    92	        logger.debug(f"Extracted {len(comments)} complete comments directly")
    93	        return comments
```

\`extract_complete_comments()\` uses the same recursive traversal pattern we saw in the API client: it walks the entire response JSON tree looking for \`commentEntityPayload\` nodes. When found, it extracts all comment fields from a single payload object — the comment text, author info (name, channel ID, avatar, verification status), engagement metrics (like count, reply count), timing, and reply metadata. Each comment is normalized into a flat dictionary with consistent keys.

### 11c. CommentFetcher (`comment_fetcher.py`)

The \`CommentFetcher\` ties the API client and parser together, orchestrating the pagination loop:

```bash
sed -n '36,158p' yt_meta/comment_fetcher.py | cat -n
```

```output
     1	    def get_comments(
     2	        self,
     3	        video_id: str,
     4	        limit: int | None = None,
     5	        sort_by: str = "top",
     6	        since_date: date | None = None,
     7	        progress_callback: Callable[[int], None] | None = None,
     8	        include_reply_continuation: bool = False,
     9	    ) -> Iterator[dict[str, Any]]:
    10	        """
    11	        Get comments from a YouTube video with comprehensive data extraction.
    12	
    13	        Args:
    14	            video_id: YouTube video ID or URL
    15	            limit: Maximum number of comments to fetch
    16	            sort_by: Sort order ("top" or "recent")
    17	            since_date: Only fetch comments after this date (requires sort_by="recent")
    18	            progress_callback: Callback function called with comment count
    19	            include_reply_continuation: Include reply continuation tokens for comments with replies
    20	
    21	        Yields:
    22	            Dict containing complete comment data, optionally including 'reply_continuation_token'
    23	        """
    24	        # Validate parameters
    25	        if since_date and sort_by != "recent":
    26	            raise ValueError("`since_date` can only be used with `sort_by='recent'`")
    27	
    28	        video_id = extract_video_id(video_id)
    29	        logger.info(f"Fetching comments for video: {video_id}")
    30	
    31	        try:
    32	            # Get initial video page data
    33	            initial_data, ytcfg = self.api_client.get_initial_video_data(video_id)
    34	
    35	            # Get comment sort endpoints with flexible detection
    36	            sort_endpoints = self.api_client.get_sort_endpoints_flexible(
    37	                initial_data, ytcfg
    38	            )
    39	
    40	            if not sort_endpoints:
    41	                logger.warning("No comment sort endpoints found")
    42	                return
    43	
    44	            # Select appropriate endpoint
    45	            continuation_token = self.api_client.select_sort_endpoint(
    46	                sort_endpoints, sort_by
    47	            )
    48	            if not continuation_token:
    49	                logger.warning(f"No continuation token found for sort_by='{sort_by}'")
    50	                return
    51	
    52	            # Fetch comments using continuation
    53	            comment_count = 0
    54	            seen_ids = set()
    55	
    56	            while continuation_token and (limit is None or comment_count < limit):
    57	                try:
    58	                    # Make API request for comments
    59	                    api_response = self.api_client.make_api_request(
    60	                        continuation_token, ytcfg
    61	                    )
    62	
    63	                    if not api_response:
    64	                        break
    65	
    66	                    # Extract complete comments directly (new approach)
    67	                    comments = self.parser.extract_complete_comments(api_response)
    68	
    69	                    # Extract reply continuation tokens if requested
    70	                    reply_tokens = {}
    71	                    if include_reply_continuation:
    72	                        reply_tokens = self.parser.extract_reply_continuations(
    73	                            api_response
    74	                        )
    75	
    76	                    # Process comments
    77	                    found_comments = False
    78	                    for comment in comments:
    79	                        if limit and comment_count >= limit:
    80	                            break
    81	
    82	                        if not comment or comment["id"] in seen_ids:
    83	                            continue
    84	
    85	                        # Apply date filtering
    86	                        if since_date and comment.get("publish_date"):
    87	                            if comment["publish_date"] < since_date:
    88	                                continue
    89	
    90	                        seen_ids.add(comment["id"])
    91	                        comment_count += 1
    92	                        found_comments = True
    93	
    94	                        # Add reply continuation token if available and requested
    95	                        if include_reply_continuation and comment["id"] in reply_tokens:
    96	                            comment["reply_continuation_token"] = reply_tokens[
    97	                                comment["id"]
    98	                            ]
    99	
   100	                        if progress_callback:
   101	                            progress_callback(comment_count)
   102	
   103	                        yield comment
   104	
   105	                    if not found_comments:
   106	                        break
   107	
   108	                    # Get next continuation token using API client
   109	                    continuation_token = self.api_client.extract_continuation_token(
   110	                        api_response
   111	                    )
   112	
   113	                except Exception as e:
   114	                    logger.error(f"Error processing comment batch: {e}")
   115	                    break
   116	
   117	        except VideoUnavailableError:
   118	            raise
   119	        except Exception as e:
   120	            logger.error(f"Error fetching comments: {e}")
   121	            raise VideoUnavailableError(
   122	                f"Could not fetch comments for video {video_id}: {e}"
   123	            ) from e
```

\`get_comments()\` is the main entry point for comment retrieval. The flow:

1. **Fetch initial page data** — gets \`ytInitialData\` and \`ytcfg\` from the watch page (line 33)
2. **Find sort endpoints** — discovers continuation tokens for "Top comments" and "Newest first" (line 36)
3. **Select the right endpoint** — picks the token matching the requested sort order (line 45)
4. **Pagination loop** (lines 56-115):
   - Makes an API request with the current continuation token
   - Extracts comments using the parser
   - Deduplicates using a \`seen_ids\` set
   - Applies date filtering if \`since_date\` is specified
   - Optionally extracts reply continuation tokens for threaded replies
   - Calls the progress callback for UI updates
   - Yields each comment and extracts the next continuation token

The generator pattern means callers can stop consuming at any time — useful for "give me the first 100 comments" scenarios without fetching thousands.

## 12. Transcript Fetcher (`transcript_fetcher.py`)

The transcript module is the simplest — it's a thin wrapper around the \`youtube-transcript-api\` library:

```bash
cat -n yt_meta/transcript_fetcher.py
```

```output
     1	import logging
     2	from typing import Dict, List
     3	from youtube_transcript_api import YouTubeTranscriptApi
     4	
     5	logger = logging.getLogger(__name__)
     6	
     7	
     8	class TranscriptFetcher:
     9	    """A fetcher for retrieving video transcripts from YouTube."""
    10	
    11	    def get_transcript(self, video_id: str, languages: List[str] = None) -> List[Dict]:
    12	        """
    13	        Fetches the transcript for a given video ID.
    14	
    15	        Args:
    16	            video_id: The ID of the YouTube video.
    17	            languages: A list of language codes to prioritize (e.g., ['en', 'de']).
    18	                       If None, it will default to English.
    19	
    20	        Returns:
    21	            A list of dictionary objects, where each object represents a
    22	            transcript snippet with 'text', 'start', and 'duration' keys.
    23	            Returns an empty list if the transcript cannot be fetched.
    24	        """
    25	        if languages is None:
    26	            languages = ["en"]
    27	        try:
    28	            transcript_list = YouTubeTranscriptApi().list(video_id)
    29	            transcript = transcript_list.find_transcript(languages)
    30	            fetched_transcript = transcript.fetch()
    31	            return [
    32	                {"text": snippet.text, "start": snippet.start, "duration": snippet.duration}
    33	                for snippet in fetched_transcript
    34	            ]
    35	        except Exception as e:
    36	            logger.error(f"Could not fetch transcript for {video_id}: {e}")
    37	            return [] ```
```

Simple and effective: it lists available transcripts for the video, finds one matching the requested language(s), fetches it, and normalizes each snippet into a \`{text, start, duration}\` dictionary. Errors are caught and logged, returning an empty list — this matches the library's philosophy of graceful degradation when content is unavailable.

## 13. The Facade: Client (`client.py`)

The \`YtMeta\` class is the public API that ties everything together. It creates and configures all the fetchers, manages the HTTP session, and provides simple methods that delegate to the appropriate internal component.

### 13a. Initialization

```bash
sed -n '19,49p' yt_meta/client.py | cat -n
```

```output
     1	class YtMeta:
     2	    """
     3	    A client for fetching metadata for YouTube videos, channels, playlists, and comments.
     4	    This class acts as a Facade, delegating calls to specialized fetcher classes.
     5	    """
     6	
     7	    def __init__(self, cache_path: str | None = None):
     8	        """
     9	        Initializes the yt-meta client.
    10	
    11	        Args:
    12	            cache_path: If provided, the path to a SQLite file for persistent,
    13	                        on-disk caching. If None (the default), caching is disabled.
    14	        """
    15	        self.session = Client(headers={"Accept-Language": "en-US,en;q=0.5"})
    16	        if cache_path:
    17	            self.cache = SQLiteCache(path=cache_path)
    18	            logger.info(f"Using SQLite cache at: {cache_path}")
    19	        else:
    20	            self.cache = DummyCache()
    21	            logger.info("Caching is disabled.")
    22	
    23	        self._video_fetcher = VideoFetcher(session=self.session, cache=self.cache)
    24	        self._channel_fetcher = ChannelFetcher(
    25	            session=self.session, cache=self.cache, video_fetcher=self._video_fetcher
    26	        )
    27	        self._playlist_fetcher = PlaylistFetcher(
    28	            session=self.session, cache=self.cache, video_fetcher=self._video_fetcher
    29	        )
    30	        self._comment_fetcher = CommentFetcher()
    31	        self._transcript_fetcher = TranscriptFetcher()
```

The constructor shows the dependency graph clearly:
- An **httpx \`Client\`** session is created with an English language header (to ensure consistent page content)
- Either a **\`SQLiteCache\`** or **\`DummyCache\`** is created based on whether \`cache_path\` was provided
- **\`VideoFetcher\`** gets the session and cache
- **\`ChannelFetcher\`** and **\`PlaylistFetcher\`** get the session, cache, AND a reference to the \`VideoFetcher\` (so they can fetch full metadata for individual videos during slow filtering)
- **\`CommentFetcher\`** and **\`TranscriptFetcher\`** are standalone — they manage their own HTTP connections

### 13b. Method Delegation

Each public method on \`YtMeta\` is a thin wrapper that resolves parameters and delegates to the right fetcher. Here's the channel videos method as an example:

```bash
sed -n '112,156p' yt_meta/client.py | cat -n
```

```output
     1	    def get_channel_videos(
     2	        self,
     3	        channel_url: str,
     4	        force_refresh: bool = False,
     5	        fetch_full_metadata: bool = False,
     6	        start_date: str | date | None = None,
     7	        end_date: str | date | None = None,
     8	        filters: dict | None = None,
     9	        stop_at_video_id: str | None = None,
    10	        max_videos: int = -1,
    11	    ) -> Generator[dict, None, None]:
    12	        """
    13	        Fetches videos from a YouTube channel's "Videos" tab.
    14	
    15	        This method handles pagination automatically and provides extensive filtering
    16	        options. It intelligently combines date parameters (`start_date`, `end_date`)
    17	        with any date conditions specified in the `filters` dictionary.
    18	
    19	        Args:
    20	            channel_url: The URL of the channel.
    21	            force_refresh: If True, bypasses the cache for the initial page load.
    22	            fetch_full_metadata: If True, performs an additional request for each
    23	                video to get its complete metadata (e.g., likes, category). This is
    24	                required for "slow filters".
    25	            start_date: The earliest publish date for videos to include.
    26	                Can be a `date` object or a string (e.g., "2023-01-01", "3 weeks ago").
    27	            end_date: The latest publish date for videos to include.
    28	            filters: A dictionary of filter conditions to apply.
    29	            stop_at_video_id: If provided, pagination will stop once this video ID
    30	                is found.
    31	            max_videos: The maximum number of videos to return (-1 for all).
    32	
    33	        Yields:
    34	            A dictionary for each video that matches the criteria.
    35	        """
    36	        return self._channel_fetcher.get_channel_videos(
    37	            channel_url,
    38	            force_refresh,
    39	            fetch_full_metadata,
    40	            start_date,
    41	            end_date,
    42	            filters,
    43	            stop_at_video_id,
    44	            max_videos,
    45	        )
```

The facade methods are intentionally thin — they accept the same parameters and delegate directly. The value is in the unified API surface: users import one class and call methods on it, rather than wiring up fetchers, sessions, and caches themselves.

## 14. End-to-End Flow Summary

Let's trace a typical call through all the layers to see how everything connects:

**Call: \`YtMeta().get_channel_videos("https://youtube.com/@SomeChannel", filters={"view_count": {"gt": 10000}})\`**

1. **\`client.py\`** → \`YtMeta.get_channel_videos()\` delegates to \`ChannelFetcher.get_channel_videos()\`

2. **\`fetchers.py\`** → \`ChannelFetcher.get_channel_videos()\`:
   - Calls \`validate_filters()\` to check the filter schema
   - Calls \`partition_filters()\` → \`view_count\` is a FAST filter, so: \`fast_filters = {"view_count": {"gt": 10000}}\`, \`slow_filters = {}\`
   - Since no slow filters, \`must_fetch_full_metadata = False\`
   - Creates the raw video generator via \`_get_raw_channel_videos_generator()\`
   - Calls \`_process_videos_generator()\`

3. **\`fetchers.py\`** → \`_get_raw_channel_videos_generator()\`:
   - Fetches the channel's \`/videos\` page HTML
   - Uses **\`parsing.py\`** → \`extract_and_parse_json(html, "ytInitialData")\` to get the page data
   - Uses **\`parsing.py\`** → \`find_ytcfg(html)\` to get the API credentials
   - Navigates to the video tab's content grid
   - Calls **\`parsing.py\`** → \`parse_video_renderer()\` for each video
   - When the first page is exhausted, uses the continuation token + \`_get_continuation_data()\` to fetch the next page

4. **\`fetchers.py\`** → \`_process_videos_generator()\`:
   - For each video yielded by the raw generator:
     - Calls **\`filtering.py\`** → \`apply_filters(video, fast_filters)\` — checks if view_count > 10000
     - Since no slow filters, skips the per-video metadata fetch
     - Yields the video to the caller

5. **Caller** receives a generator of video dicts, each with \`view_count > 10000\`

The entire pipeline is lazy — videos are fetched and filtered one page at a time, and the caller can stop consuming at any point to avoid unnecessary requests.
