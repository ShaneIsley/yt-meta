# yt-meta

A Python library for finding video and channel metadata from YouTube.

## Purpose

This library collects metadata for YouTube videos, channels, and playlists. It handles network requests, data parsing, and pagination so you can focus on your analysis.

## Architecture

`yt-meta` uses a **Facade** pattern. The `YtMeta` class provides a unified interface for all fetching operations, delegating calls to specialized `Fetcher` classes.

-   **`VideoFetcher`**: Fetches video metadata.
-   **`ChannelFetcher`**: Fetches channel metadata, video lists, and shorts.
-   **`PlaylistFetcher`**: Fetches playlist details.
-   **`CommentFetcher`**: Fetches comments and replies for videos.
-   **`TranscriptFetcher`**: Fetches video transcripts.

This architecture keeps the codebase clean, organized, and easy to maintain.

## Installation

This project uses `uv` for package management. You can install `yt-meta` from PyPI:

```bash
uv pip install yt-meta
```

Persistent caching requires an optional dependency:

```bash
# For disk-based caching
uv pip install "yt-meta[persistent_cache]"
```

## Core Features

### 1. Get Video Metadata

Fetches metadata for a specific YouTube video.

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

### 5. Get All Shorts from a Channel

You can fetch all Shorts from a channel. Both a fast path (basic metadata) and a slow path (full metadata) are supported.

**Fast Path Example:**

The fast path is the most efficient way to list shorts, but provides limited metadata.

```python
import itertools
from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@bashbunni"
shorts_generator = client.get_channel_shorts(channel_url)

# Print the first 5 shorts
for short in itertools.islice(shorts_generator, 5):
    print(f"- {short['title']} (ID: {short['video_id']})")
```

**Slow Path Example (Full Metadata):**

Set `fetch_full_metadata=True` to retrieve all details for each short, such as `like_count` and `publish_date`.

```python
import itertools
from yt_meta import YtMeta

client = YtMeta()
channel_url = "https://www.youtube.com/@bashbunni"
shorts_generator = client.get_channel_shorts(
    channel_url,
    fetch_full_metadata=True
)

# Print the first 5 shorts with full metadata
for short in itertools.islice(shorts_generator, 5):
    likes = short.get('like_count', 'N/A')
    print(f"- {short['title']} (Likes: {likes})")
```

### 6. Get Video Comments

Fetches comments for a given video, sorted by **"Top comments"** (default) or **"Most Recent"**. Returns a generator yielding standardized comment data.

**Example:**

```python
import itertools
from yt_meta import YtMeta

client = YtMeta()
video_url = "https://www.youtube.com/watch?v=B68agR-OeJM"

# Fetch the 5 most recent comments
print("--- Most Recent Comments ---")
recent_comments = client.get_video_comments(
    video_url,
    sort_by='recent', # or 'top'
    limit=5
)
for comment in recent_comments:
    print(f"- Text: '{comment['text'][:80]}...'")
    print(f"  - Author: {comment['author']} (Channel ID: {comment['author_channel_id']})")
    print(f"  - Replies: {comment['reply_count']} | Is Reply: {comment['is_reply']}")

# Fetch the 5 top comments
print("\n--- Top Comments ---")
top_comments = client.get_video_comments(
    video_url,
    sort_by='top',
    limit=5
)
for comment in top_comments:
    print(f"- Text: '{comment['text'][:80]}...'")
    print(f"  - Author: {comment['author']} (Likes: {comment['like_count']})")
    print(f"  - Replies: {comment['reply_count']} | Is Reply: {comment['is_reply']}")
```

#### Fetching Comments Since a Specific Date

Pass the `since_date` parameter to fetch comments posted after a specific date. This feature **requires `sort_by='recent'`**. The library fetches comment pages until it finds one older than the target date, then stops to minimize network requests.

**Example:**
```python
from datetime import date, timedelta
from yt_meta import YtMeta

client = YtMeta()
video_url = "https://www.youtube.com/watch?v=B68agR-OeJM"

# Get comments from the last 30 days
thirty_days_ago = date.today() - timedelta(days=30)

recent_comments = client.get_video_comments(
    video_url,
    sort_by='recent',
    since_date=thirty_days_ago,
    limit=500 # The fetch will stop before this if all recent comments are found
)

for comment in recent_comments:
    print(f"- {comment['publish_date']}: {comment['text'][:80]}...")
```

### 7. Get Video Transcript

Fetches the transcript (subtitles) for a given video. Specify preferred languages; the client returns the first available match.

**Example:**
```python
from yt_meta import YtMeta

client = YtMeta()
video_id = "dQw4w9WgXcQ"

# Fetch the default transcript
transcript = client.get_video_transcript(video_id)
if transcript:
    print("Transcript found. Showing the first 5 snippets:")
    for snippet in transcript[:5]:
        start_time = snippet["start"]
        text = snippet["text"].replace("\\n", " ")
        print(f"- [{start_time:.2f}s] {text}")
else:
    print("No transcript found.")

# Fetch a transcript in a specific language (e.g., Spanish)
# The client will try 'es' first, then fall back to 'en' if Spanish is not available.
print("\n--- Attempting to fetch Spanish transcript ---")
spanish_transcript = client.get_video_transcript(video_id, languages=['es', 'en'])
if spanish_transcript:
    print("Transcript found. Showing the first 5 snippets of the best available match:")
    for snippet in spanish_transcript[:5]:
        start_time = snippet["start"]
        text = snippet["text"].replace("\\n", " ")
        print(f"- [{start_time:.2f}s] {text}")
else:
    print("No transcript found for the specified languages.")
```

## Caching

`yt-meta` includes a flexible caching system to improve performance and avoid re-fetching data from YouTube.

### Default In-Memory Cache

By default, `YtMeta` uses a simple in-memory dictionary to cache results. This cache is temporary and only lasts for the lifetime of the client instance.

```python
from yt_meta import YtMeta

client = YtMeta()
# The first call will fetch from the network
meta1 = client.get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
# This second call will be instant, served from the in-memory cache
meta2 = client.get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
```

### Persistent Caching

To cache results across runs or scripts, pass a **persistent, dictionary-like object** to the client. The library provides an optional `diskcache` integration.

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
metadata = client.get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
```

Any object implementing the `MutableMapping` protocol (e.g., `__getitem__`, `__setitem__`, `__delitem__`) works as a cache via the `cache=` kwarg — plain `dict` for in-memory, `diskcache.Cache` for disk-backed, or `sqlitedict.SqliteDict` if you `pip install sqlitedict` yourself. See `examples/features/19_alternative_caching_sqlite.py` for the built-in SQLite path via `cache_path=`.

## Advanced Features

### Filtering Videos, Shorts, and Comments

The `filters` argument on `get_channel_videos`, `get_channel_shorts`, and `get_video_comments` selects items matching specific criteria.

#### Robust Filter Validation
`yt-meta` validates your `filters` dictionary *before* making any network requests. If you provide a nonexistent field, an invalid operator, or an incorrect value type, the library raises a `ValueError` or `TypeError`.

This fail-fast design stops you from discovering typos only after a slow query completes. See `examples/features/23_filter_validation.py` for a demonstration.

#### Two-Stage Filtering: Fast vs. Slow

The library uses an efficient two-stage filtering process for videos and shorts:

*   **Fast Filters:** Applied first, using metadata available on the main channel or playlist page (e.g., `title`, `view_count`). This is very efficient.
*   **Slow Filters:** Applied second, only on items that pass the fast filters. This requires fetching full metadata for each item individually, which is much slower.

The client automatically detects when a slow filter is used and sets `fetch_full_metadata=True` for you.

> [!NOTE]
> Comment filtering does not use the fast/slow system. All comment filters apply after fetching comment data.

#### Missing-field semantics

If a filter targets a field that's missing or `None` on a particular video, the video is **dropped** from the result — it can't match the filter. This is the right default for the common case (`publish_date >= 2023` should not include videos with no publish_date), but it can surprise users who expect "filter on a field that doesn't exist on every video" to behave differently. To investigate when drops happen, enable `logging.DEBUG` on the `yt_meta.filtering` logger — each drop emits a debug line with the video id and the missing field. See M6 in the v0.6.0 CHANGELOG.

#### Supported Fields and Operators

The following table lists supported fields and their valid operators. Validation enforces these rules.

| Field                 | Supported Operators              | Content Type(s)                                             | Filter Speed |
| :-------------------- | :------------------------------- | :---------------------------------------------------------- | :----------- |
| `title`               | `contains`, `re`, `eq`           | Video, Short                                                | Fast         |
| `description_snippet` | `contains`, `re`, `eq`           | Video                                                       | Fast         |
| `view_count`          | `gt`, `gte`, `lt`, `lte`, `eq`   | Video, Short                                                | Fast         |
| `duration_seconds`    | `gt`, `gte`, `lt`, `lte`, `eq`   | Video, Short                                                | Fast         |
| `publish_date`        | `gt`, `gte`, `lt`, `lte`, `eq`   | Video, Short, Comment                                       | Fast (Video), **Slow** (Short, Playlist) |
| `like_count`          | `gt`, `gte`, `lt`, `lte`, `eq`   | Video, Short, Comment                                       | **Slow**     |
| `category`            | `contains`, `re`, `eq`           | Video, Short                                                | **Slow**     |
| `keywords`            | `contains_any`, `contains_all` | Video, Short                                                | **Slow**     |
| `full_description`    | `contains`, `re`, `eq`           | Video                                                       | **Slow**     |
| `text`                | `contains`, `re`, `eq`           | Comment                                                     | N/A          |
| `is_by_owner`         | `eq`                             | Comment                                                     | N/A          |
| `is_reply`            | `eq`                             | Comment                                                     | N/A          |
| `is_hearted_by_owner` | `eq`                             | Comment                                                     | N/A          |

> [!NOTE]
> Some fields like `publish_date` can be "fast" for channel videos but "slow" for shorts or playlists because the basic metadata is not always available on those pages.

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
> When filtering a playlist by date, the library fetches metadata for **all** videos first, as playlists may not be chronological. Large playlists will be slow.

> **Important Note on Shorts Filtering:**
> Similarly, the Shorts feed does not provide a publish date on its fast path. Any date-based filter on `get_channel_shorts` will automatically trigger the slower, full metadata fetch for each short.

## Logging

`yt-meta` uses Python's `logging` module. Configure a basic logger to see log output.

**Example:**
```python
import logging

# Configure logging to print INFO-level messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Now, when you use the client, you will see logs
# ...
```

## API Reference

### `YtMeta(cache_path=None, cache=None, cache_ttl_seconds=86400, accept_cookies=False)`

The main client for interacting with the library. Handles session management and delegates work to specialized fetcher classes.

-   **`cache_path`**: Optional path to a SQLite file for persistent on-disk caching. The library opens and manages the file.
-   **`cache`**: Optional pre-built `MutableMapping` (e.g. a plain `dict` for in-memory caching, or a `diskcache.Cache` / `sqlitedict` instance for persistent). Takes precedence over `cache_path`. If both are `None`, caching is disabled.
-   **`cache_ttl_seconds`**: TTL (seconds) for entries in the built-in SQLite cache. Default `86400` (1 day). Ignored when you inject your own `cache`.
-   **`accept_cookies`**: Opt in to bypassing YouTube's EU cookie-consent wall. Default `False` (no consent cookie is set). If a call fails with a `302` redirect to `consent.youtube.com` (region-gated, e.g. the EU), construct the client with `YtMeta(accept_cookies=True)` — a `SOCS` consent cookie is then set on the session so YouTube serves content directly. This is an explicit, conscious choice to accept YouTube's cookies on your behalf, which is why it's opt-in rather than automatic.

#### `get_video_metadata(youtube_url: str) -> dict`
Fetches metadata for a single YouTube video.
-   **`youtube_url`**: The full URL of the YouTube video.
-   **Returns**: A dictionary containing metadata such as `title`, `description`, `view_count`, `like_count`, `publish_date` (a `datetime` — see M4 in the v0.6.0 CHANGELOG), `category`, and more. Returns `None` when the watch page was fetched successfully but can't be parsed (typically: ongoing live streams, just-deleted videos, A/B-tested page-structure variants — see M7 in the v0.6.0 CHANGELOG).
-   **Raises**: `VideoUnavailableError` if the HTTP fetch itself fails (network error, 404, rate-limit). Distinct from the `None` return for parse failures.

#### `get_video_comments(youtube_url: str, limit: int | None = 100, sort_by: str = 'recent', progress_callback=None, since_date=None, filters: dict | None = None) -> Generator[dict, None, None]`
Fetches comments for a specific YouTube video.
-   **`youtube_url`**: The full URL of the YouTube video (any of `watch?v=...`, `youtu.be/...`, `/shorts/...`, or a bare 11-char id).
-   **`limit`**: Max comments to fetch. Defaults to `100`. Pass `None` or `-1` for unbounded — but you must also pass `since_date` (safety guard against runaway pagination on popular videos).
-   **`sort_by`**: `'recent'` (default — chronological, required for `since_date` short-circuit) or `'top'` (YouTube's editorial ranking).
-   **`since_date`**: A `date`, `datetime`, or `'YYYY-MM-DD'` string. The only filter that short-circuits pagination — when combined with `sort_by='recent'`, fetching stops at the first older-than-cutoff comment.
-   **`filters`**: Comment-level predicates applied after fetch (see the filter table below). These operate on the in-memory comment list and do NOT reduce request count — they're convenience predicates, not server-side narrowing. Use `since_date` for request reduction.
-   **Returns**: A generator that yields a standardized dictionary for each comment.

#### `get_channel_metadata(channel_url: str) -> dict`
Fetches metadata for a specific channel. The client caches results.
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

## Library Architecture

`yt-meta` follows the **Facade design pattern**.

- **`YtMeta` (The Facade):** The public-facing API. It delegates requests to the appropriate fetcher class and holds shared objects like the session and cache, but contains no data-fetching logic.

- **Fetcher Classes (The Subsystems):**
  - **`VideoFetcher`:** Fetches single-video metadata (title, description, view count, etc.).
  - **`ChannelFetcher`:** Fetches data from a channel's "Videos" and "Shorts" tabs, including pagination.
  - **`PlaylistFetcher`:** Retrieves video lists from a playlist.
  - **`CommentFetcher`:** Fetches comments and replies for videos.
  - **`TranscriptFetcher`:** Fetches video transcripts.

This design makes the library easier to maintain, test, and extend. To fix a playlist parsing bug, look in `yt_meta/fetchers.py` in the `PlaylistFetcher` class.