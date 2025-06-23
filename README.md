# yt-meta

A Python library for finding video and channel metadata from YouTube.

## Purpose

This library is designed to provide a simple and efficient way to collect metadata for YouTube videos and channels, such as titles, view counts, likes, and descriptions. It is built to support data analysis, research, or any application that needs structured information from YouTube.

## Installation

You can install `yt-meta` from PyPI:

```bash
pip install yt-meta
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
    print(f"- {video['title']} (ID: {video['videoId']})")
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
    print(f"- {video['title']} (ID: {video['videoId']})")
```

### 5. Filtering Channel Videos by Date

You can efficiently filter videos by a date range using the `start_date` and `end_date` arguments. The library automatically stops fetching older videos once it passes the `start_date`, saving time and network requests.

The date arguments can be a `datetime.date` object or a string in two formats:
*   **Shorthand:** `"1d"`, `"2w"`, `"3m"`, `"4y"` (days, weeks, months, years)
*   **Human-readable:** `"1 day ago"`, `"2 weeks ago"`

**Example:**

```python
from datetime import date, timedelta
from yt_meta import YtMetaClient
import itertools

client = YtMetaClient()
channel_url = "https://www.youtube.com/@samwitteveenai/videos"

# Get videos from the last 30 days
print("\n--- Videos from the last 30 days ---")
recent_videos = client.get_channel_videos(channel_url, start_date="30d")
for video in itertools.islice(recent_videos, 5):
    print(f"- {video.get('title')}")

# Get videos from a specific window (90 to 60 days ago)
print("\n--- Videos from a specific 30-day window in the past ---")
start = date.today() - timedelta(days=90)
end = date.today() - timedelta(days=60)
window_videos = client.get_channel_videos(channel_url, start_date=start, end_date=end)
for video in itertools.islice(window_videos, 5):
    print(f"- {video.get('title')}")
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

#### `get_channel_videos(channel_url: str, fetch_full_metadata: bool = False, start_date: Optional[Union[str, date]] = None, end_date: Optional[Union[str, date]] = None) -> Generator[dict, None, None]`
Returns a generator that yields metadata for all videos on a channel's "Videos" tab. It handles pagination automatically.
-   **`channel_url`**: URL of the channel's "Videos" tab.
-   **`fetch_full_metadata`**: If `True`, fetches the complete, detailed metadata for each video. This is slower as it requires an additional request per video. If `False` (default), returns basic metadata available directly from the channel page.
-   **`start_date`**: The earliest date for videos to include. Can be a `datetime.date` object or a string (e.g., `"30d"`, `"2 months ago"`). The generator will efficiently stop once it encounters videos older than this date.
-   **`end_date`**: The latest date for videos to include. Can be a `datetime.date` object or a string.
-   **Yields**: Dictionaries of video metadata. The contents depend on the `fetch_full_metadata` flag.

#### `get_playlist_videos(playlist_id: str, fetch_full_metadata: bool = False) -> Generator[dict, None, None]`
Returns a generator that yields metadata for all videos in a playlist. It handles pagination automatically.
-   **`playlist_id`**: The ID of the playlist (e.g., `PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU`).
-   **`fetch_full_metadata`**: If `True`, fetches the complete, detailed metadata for each video. This is slower as it requires an additional request per video. If `False` (default), returns basic metadata available directly from the playlist page.
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
