# yt-meta

A Python library for finding video and channel metadata from YouTube.

## Purpose

This library is designed to provide a simple and efficient way to collect metadata for YouTube videos and channels, such as titles, view counts, likes, and descriptions. It is built to support data analysis, research, or any application that needs structured information from YouTube.

## Installation

This project uses `uv` for package management. You can install `yt-meta` from PyPI:

```bash
uv pip install yt-meta
```

## Inspiration

This project extends the great `youtube-comment-downloader` library, inheriting its session management while adding additional metadata capabilities.

## Core Features

The library offers several ways to fetch metadata.

### 1. Get Video Metadata

Fetches comprehensive metadata for a specific YouTube video.

**Example:**

```python
from yt_meta import YtMetaClient

client = YtMetaClient()
video_url = "https://www.youtube.com/watch?v=B68agR-OeJM"
metadata = client.get_video_metadata(video_url)
print(f"Title: {metadata['title']}")
```

### 2. Get Channel Metadata

Fetches metadata for a specific YouTube channel.

**Example:**

```python
from yt_meta import YtMetaClient

client = YtMetaClient()
channel_url = "https://www.youtube.com/@samwitteveenai"
channel_metadata = client.get_channel_metadata(channel_url)
print(f"Channel Name: {channel_metadata['title']}")
```

### 3. Get All Videos from a Channel

Returns a generator that yields metadata for all videos on a channel's "Videos" tab, handling pagination automatically.

**Example:**
```python
import itertools
from yt_meta import YtMetaClient

client = YtMetaClient()
channel_url = "https://www.youtube.com/@AI-Makerspace/videos"
videos_generator = client.get_channel_videos(channel_url)

# Print the first 5 videos
for video in itertools.islice(videos_generator, 5):
    print(f"- {video['title']} (ID: {video['video_id']})")
```

### 4. Get All Videos from a Playlist

Returns a generator that yields metadata for all videos in a playlist, handling pagination automatically.

**Example:**
```python
import itertools
from yt_meta import YtMetaClient

client = YtMetaClient()
playlist_id = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"
videos_generator = client.get_playlist_videos(playlist_id)

# Print the first 5 videos
for video in itertools.islice(videos_generator, 5):
    print(f"- {video['title']} (ID: {video['video_id']})")
```

### 5. Filtering Videos

The library provides a powerful filtering system via the `filters` argument, available on both `get_channel_videos` and `get_playlist_videos`. This allows you to find videos matching specific criteria.

#### Two-Stage Filtering: Fast vs. Slow

The library uses an efficient two-stage filtering process:

*   **Fast Filters:** Applied first, using metadata that is available on the main channel or playlist page (e.g., `title`, `view_count`). This is very efficient.
*   **Slow Filters:** Applied second, only on videos that pass the fast filters. This requires fetching full metadata for each video individually, which is much slower.

The client automatically detects when a slow filter is used and sets `fetch_full_metadata=True` for you.

**Supported Fields and Operators:**

| Field                 | Supported Operators              | Filter Type                                                 |
| :-------------------- | :------------------------------- | :---------------------------------------------------------- |
| `title`               | `contains`, `re`, `eq`           | Fast                                                        |
| `description_snippet` | `contains`, `re`, `eq`           | Fast                                                        |
| `view_count`          | `gt`, `gte`, `lt`, `lte`, `eq`   | Fast                                                        |
| `duration_seconds`    | `gt`, `gte`, `lt`, `lte`, `eq`   | Fast                                                        |
| `publish_date`        | `gt`, `gte`, `lt`, `lte`, `eq`   | **Slow** (Automatic full metadata fetch)                    |
| `like_count`          | `gt`, `gte`, `lt`, `lte`, `eq`   | **Slow** (Automatic full metadata fetch)                    |
| `category`            | `contains`, `re`, `eq`           | **Slow** (Automatic full metadata fetch)                    |
| `keywords`            | `contains_any`, `contains_all` | **Slow** (Automatic full metadata fetch)                    |
| `full_description`    | `contains`, `re`, `eq`           | **Slow** (Automatic full metadata fetch)                    |

#### Example: Basic Filtering (Fast)

This example finds popular, short videos. Since both `view_count` and `duration_seconds` are fast filters, this query is very efficient.

```python
import itertools
from yt_meta import YtMetaClient

client = YtMetaClient()
channel_url = "https://www.youtube.com/@TED/videos"

# Find videos over 1M views AND shorter than 5 minutes (300s)
adv_filters = {
    "view_count": {"gt": 1_000_000},
    "duration_seconds": {"lt": 300}
}

# This is fast because both view_count and duration are available
# in the basic metadata returned from the main channel page.
videos = client.get_channel_videos(
    channel_url,
    filters=adv_filters
)

for video in itertools.islice(videos, 5):
    views = video.get('view_count', 0)
    duration = video.get('duration_seconds', 0)
    print(f"- {video.get('title')} ({views:,} views, {duration}s)")
```

#### Example: Filtering by Date

Filtering by `publish_date` is a "slow" filter, but the library optimizes it for channels by using the approximate date text to avoid paginating through the entire channel history when possible.

You can provide `datetime.date` objects or a relative date string.

**Using `datetime.date` objects:**

```python
from datetime import date
from yt_meta import YtMetaClient
import itertools

client = YtMetaClient()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Get videos from a specific window
start = date(2025, 4, 1)
end = date(2025, 6, 30)

date_filters = {"publish_date": {"gte": start, "lte": end}}
videos = client.get_channel_videos(channel_url, filters=date_filters)

for video in itertools.islice(videos, 5):
    print(f"- {video.get('title')}")
```

**Using relative date strings:**

To use shorthand relative dates (e.g., `"30d"`), you must use the `parse_relative_date_string` helper.

```python
from yt_meta import YtMetaClient
from yt_meta.date_utils import parse_relative_date_string
import itertools

client = YtMetaClient()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

thirty_days_ago = parse_relative_date_string("30d")
date_filters = {"publish_date": {"gte": thirty_days_ago}}

recent_videos = client.get_channel_videos(channel_url, filters=date_filters)
for video in itertools.islice(recent_videos, 5):
    print(f"- {video.get('title')}")
```

> **Important Note on Playlist Filtering:**
> When filtering a playlist by date, the library must fetch metadata for **all** videos first, as playlists are not guaranteed to be chronological. This can be very slow for large playlists.

#### Example: Combining Slow Filters

This example finds videos in the "Comedy" category, tagged with the keyword "skit," and published after the start of 2023. The client handles fetching the required metadata automatically.

```python
import itertools
from datetime import date
from yt_meta import YtMetaClient

client = YtMetaClient()
channel_url = "https://www.youtube.com/@TheAIEpiphany/videos"

adv_filters = {
    "category": {"eq": "Comedy"},
    "keywords": {"contains_any": ["skit", "sketch"]},
    "publish_date": {"gte": date(2023, 1, 1)}
}

# The client will automatically set `fetch_full_metadata=True`
# because "category", "keywords", and "publish_date" are slow filters.
videos = client.get_channel_videos(channel_url, filters=adv_filters)

for video in itertools.islice(videos, 5):
    title = video.get('title', 'N/A')
    category = video.get('category', 'N/A')
    p_date = video.get('publish_date', 'N/A')
    print(f"- {title} (Category: {category}, Published: {p_date})")
```

## Logging

`yt-meta` uses Python's `logging` module to provide insights into its operations. To see the log output, you can configure a basic logger.

**Example:**
```python
import logging

# Configure logging to print INFO-level messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Now, when you use the client, you will see logs
# ...
```

## API Reference

### `YtMetaClient()`

The main client for interacting with the library. It inherits from `youtube-comment-downloader` and handles session management and caching.

#### `get_video_metadata(youtube_url: str) -> dict`
Fetches comprehensive metadata for a single YouTube video.
-   **`youtube_url`**: The full URL of the YouTube video.
-   **Returns**: A dictionary containing metadata such as `title`, `description`, `view_count`, `like_count`, `publish_date`, `category`, and more.
-   **Raises**: `VideoUnavailableError` if the video page cannot be fetched or the video is private/deleted.

#### `get_channel_metadata(channel_url: str, force_refresh: bool = False) -> dict`
Fetches metadata for a YouTube channel.
-   **`channel_url`**: The URL of the channel's main page or "Videos" tab.
-   **`force_refresh`**: If `True`, bypasses the internal cache and fetches fresh data.
-   **Returns**: A dictionary with channel metadata like `title`, `description`, `subscriber_count`, `vanity_url`, etc.
-   **Raises**: `VideoUnavailableError`, `MetadataParsingError`.

#### `get_channel_videos(channel_url: str, force_refresh: bool = False, fetch_full_metadata: bool = False, start_date: Optional[Union[str, date]] = None, end_date: Optional[Union[str, date]] = None, filters: Optional[dict] = None) -> Generator[dict, None, None]`
Returns a generator that yields metadata for all videos on a channel's "Videos" tab. It handles pagination automatically.
-   **`channel_url`**: URL of the channel's "Videos" tab.
-   **`force_refresh`**: If `True`, bypasses the cache for the initial page load.
-   **`fetch_full_metadata`**: If `True`, fetches the complete, detailed metadata for each video. This is slower as it requires an additional request per video. If `False` (default), returns basic metadata available directly from the channel page.
-   **`start_date`**: The earliest date for videos to include. Can be a `datetime.date` object or a string (e.g., `"30d"`, `"2 months ago"`). The generator will efficiently stop once it encounters videos older than this date.
-   **`end_date`**: The latest date for videos to include. Can be a `datetime.date` object or a string.
-   **`filters`**: A dictionary for advanced filtering (e.g., `{"view_count": {"gt": 1000}}`).
-   **Yields**: Dictionaries of video metadata. The contents depend on the `fetch_full_metadata` flag.

#### `get_playlist_videos(playlist_id: str, fetch_full_metadata: bool = False, start_date: Optional[Union[str, date]] = None, end_date: Optional[Union[str, date]] = None, filters: Optional[dict] = None) -> Generator[dict, None, None]`
Returns a generator that yields metadata for all videos in a playlist. It handles pagination automatically.
-   **`playlist_id`**: The ID of the playlist (e.g., `PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU`).
-   **`fetch_full_metadata`**: If `True`, fetches the complete, detailed metadata for each video. This is slower as it requires an additional request per video. If `False` (default), returns basic metadata available directly from the playlist page.
-   **`start_date`**: The earliest date for videos to include. Can be a `datetime.date` object or a string.
-   **`end_date`**: The latest date for videos to include. Can be a `datetime.date` object or a string.
-   **`filters`**: A dictionary for advanced filtering (e.g., `{"duration_seconds": {"lte": 60}}`).
-   **Yields**: Dictionaries of video metadata.

#### `clear_cache(channel_url: str = None)`
Clears the internal in-memory cache.
-   **`channel_url`**: If provided, clears the cache for only that specific channel. If `None` (default), the entire cache is cleared.

## Error Handling

The library uses custom exceptions to signal specific error conditions.

### `YtMetaError`
The base exception for all errors in this library.

### `MetadataParsingError`
Raised when the necessary metadata (e.g., the `ytInitialData` JSON object) cannot be found or parsed from the YouTube page. This can happen if YouTube changes its page structure.

### `VideoUnavailableError`
Raised when a video or channel page cannot be fetched. This could be due to a network error, a deleted/private video, or an invalid URL.
