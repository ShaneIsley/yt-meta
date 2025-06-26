# yt-meta

A Python library for finding video and channel metadata from YouTube.

## Purpose

This library is designed to provide a simple and efficient way to collect metadata for YouTube videos and channels, such as titles, view counts, likes, and descriptions. It is built to support data analysis, research, or any application that needs structured information from YouTube.

## Installation

This project uses `uv` for package management. You can install `yt-meta` from PyPI:

```bash
uv pip install yt-meta
```

To enable persistent caching, you need to install an optional dependency:

```bash
# For disk-based caching
uv pip install "yt-meta[persistent_cache]"
```

## Inspiration

This project extends the great `youtube-comment-downloader` library, inheriting its session management while adding additional metadata capabilities.

## Core Features

The library offers several ways to fetch metadata.

### 1. Get Video Metadata

Fetches comprehensive metadata for a specific YouTube video.

**Example:**

```python
from yt_meta import YtMeta

client = YtMeta()
video_url = "https://www.youtube.com/watch?v=B68agR-OeJM"
metadata = client.get_video_metadata(video_url)
print(f"Title: {metadata['title']}")
```

### 2. Get Channel Metadata

Fetches metadata for a specific YouTube channel.

**Example:**

```python
from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai"
channel_metadata = client.get_channel_metadata(channel_url)
print(f"Channel Name: {channel_metadata['title']}")
```

### 3. Get All Videos from a Channel

Returns a generator that yields metadata for all videos on a channel's "Videos" tab, handling pagination automatically.

**Example:**
```python
import itertools
from yt_meta import YtMeta

client = YtMeta()
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
from yt_meta import YtMeta

client = YtMeta()
playlist_id = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"
videos_generator = client.get_playlist_videos(playlist_id)

# Print the first 5 videos
for video in itertools.islice(videos_generator, 5):
    print(f"- {video['title']} (ID: {video['video_id']})")
```

## Caching

`yt-meta` includes a flexible caching system to improve performance and avoid re-fetching data from YouTube.

### Default In-Memory Cache

By default, `YtMeta` uses a simple in-memory dictionary to cache results. This cache is temporary and only lasts for the lifetime of the client instance.

```python
client = YtMeta()
# The first call will fetch from the network
meta1 = client.get_video_metadata("some_url") 
# This second call will be instant, served from the in-memory cache
meta2 = client.get_video_metadata("some_url") 
```

### Persistent Caching

For caching results across different runs or scripts, you can provide a **persistent, dictionary-like object** to the client. The library provides an optional `diskcache` integration for this purpose.

First, install the necessary extra:
```bash
uv pip install "yt-meta[persistent_cache]"
```

Then, instantiate a `diskcache.Cache` object and pass it to the client:

```python
from yt_meta import YtMeta
from diskcache import Cache

# The cache object can be any dict-like object.
# Here, we use diskcache for a persistent, file-based cache.
persistent_cache = Cache(".my_yt_meta_cache")

client = YtMeta(cache=persistent_cache)

# The first time this script runs, it will be slow (fetches from network).
# Subsequent runs will be very fast, reading directly from the disk cache.
metadata = client.get_video_metadata("some_url")
```

Any object that implements the `MutableMapping` protocol (e.g., `__getitem__`, `__setitem__`, `__delitem__`) can be used as a cache. See `examples/features/19_alternative_caching_sqlite.py` for a demonstration using `sqlitedict`.

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
| `publish_date`        | `gt`, `gte`, `lt`, `lte`, `eq`   | Fast                                                        |
| `like_count`          | `gt`, `gte`, `lt`, `lte`, `eq`   | **Slow** (Automatic full metadata fetch)                    |
| `category`            | `contains`, `re`, `eq`           | **Slow** (Automatic full metadata fetch)                    |
| `keywords`            | `contains_any`, `contains_all` | **Slow** (Automatic full metadata fetch)                    |
| `full_description`    | `contains`, `re`, `eq`           | **Slow** (Automatic full metadata fetch)                    |

#### Example: Basic Filtering (Fast)

This example finds popular, short videos. Since both `view_count` and `duration_seconds` are fast filters, this query is very efficient.

```python
import itertools
from yt_meta import YtMeta

client = YtMeta()
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

The easiest way to filter by date is to use the `start_date` and `end_date` arguments. The library also optimizes this for channels by stopping the search early once videos are older than the specified `start_date`.

You can provide `datetime.date` objects or a relative date string (e.g., `"30d"`, `"6 months ago"`).

**Using `datetime.date` objects:**

```python
from datetime import date
from yt_meta import YtMeta
import itertools

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Get videos from a specific window
start = date(2024, 1, 1)
end = date(2024, 3, 31)

videos = client.get_channel_videos(
    channel_url,
    start_date=start,
    end_date=end
)

for video in itertools.islice(videos, 5):
    p_date = video.get('publish_date', 'N/A')
    print(f"- {video.get('title')} (Published: {p_date})")
```

**Using relative date strings:**

```python
from yt_meta import YtMeta
import itertools

client = YtMeta()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

recent_videos = client.get_channel_videos(
    channel_url,
    start_date="6 months ago"
)

for video in itertools.islice(recent_videos, 5):
    p_date = video.get('publish_date', 'N/A')
    print(f"- {video.get('title')} (Published: {p_date})")
```

> **Important Note on Playlist Filtering:**
> When filtering a playlist by date, the library must fetch metadata for **all** videos first, as playlists are not guaranteed to be chronological. This can be very slow for large playlists.

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

### `YtMeta(cache: Optional[MutableMapping] = None)`

The main client for interacting with the library. It inherits from `youtube-comment-downloader` and handles session management.

-   **`cache`**: An optional dictionary-like object to use for caching. If `None`, a temporary in-memory cache is used.

#### `get_video_metadata(youtube_url: str) -> dict`
Fetches comprehensive metadata for a single YouTube video.
-   **`youtube_url`**: The full URL of the YouTube video.
-   **Returns**: A dictionary containing metadata such as `title`, `description`, `view_count`, `like_count`, `publish_date`, `category`, and more.
-   **Raises**: `VideoUnavailableError` if the video page cannot be fetched or the video is private/deleted.

#### `get_channel_metadata(channel_url: str) -> dict`
Fetches metadata for a specific channel. Results are cached.
-   **`channel_url`**: The URL of the channel.
-   **Returns**: A dictionary with channel metadata like `title`, `description`, `subscriber_count`, `vanity_url`, etc.
-   **Raises**: `VideoUnavailableError`, `MetadataParsingError`.

#### `get_channel_videos(channel_url: str, ..., stop_at_video_id: str = None, max_videos: int = -1) -> Generator[dict, None, None]`
Yields metadata for videos from a channel.
-   **`start_date`**: The earliest date for videos to include (e.g., `date(2023, 1, 1)` or `"30d"`).
-   **`end_date`**: The latest date for videos to include.
-   **`fetch_full_metadata`**: If `True`, fetches detailed metadata for every video. Automatically enabled if a "slow filter" is used.
-   **`filters`**: A dictionary of advanced filter conditions (see above).
-   **`stop_at_video_id`**: Stops fetching when this video ID is found.
-   **`max_videos`**: The maximum number of videos to return.

#### `get_playlist_videos(playlist_id: str, ..., stop_at_video_id: str = None, max_videos: int = -1) -> Generator[dict, None, None]`
Yields metadata for videos from a playlist.
-   **`start_date`**: The earliest date for videos to include (e.g., `date(2023, 1, 1)` or `"30d"`).
-   **`end_date`**: The latest date for videos to include.
-   **`fetch_full_metadata`**: If `True`, fetches detailed metadata for every video.
-   **`filters`**: A dictionary of advanced filter conditions.
-   **`stop_at_video_id`**: Stops fetching when this video ID is found.
-   **`max_videos`**: The maximum number of videos to return.

#### `clear_cache()`
Clears all items from the configured cache (both in-memory and persistent).

## Error Handling

The library uses custom exceptions to signal specific error conditions.

### `YtMetaError`
The base exception for all errors in this library.

### `MetadataParsingError`
Raised when the necessary metadata (e.g., the `ytInitialData` JSON object) cannot be found or parsed from the YouTube page. This can happen if YouTube changes its page structure.

### `VideoUnavailableError`
Raised when a video or channel page cannot be fetched. This could be due to a network error, a deleted/private video, or an invalid URL.
