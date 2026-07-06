# yt-meta

A Python library for finding video and channel metadata from YouTube.

## Purpose

yt-meta collects metadata for YouTube videos, channels, playlists, comments, and transcripts. It handles the network requests, parsing, and pagination.

## Architecture

`yt-meta` uses a **Facade** pattern. The `YtMeta` class provides a unified interface for all fetching operations, delegating calls to specialized `Fetcher` classes.

-   **`VideoFetcher`**: Fetches single-video metadata (incl. availability status).
-   **`ChannelFetcher`**: Fetches channel metadata, the Videos / Shorts / Live (streams) tabs, and pagination.
-   **`PlaylistFetcher`**: Fetches playlist details.
-   **`CommentFetcher`**: Fetches comments and replies for videos.
-   **`TranscriptFetcher`**: Fetches video transcripts.

The package ships type annotations (`py.typed`), so IDEs and type-checkers pick up signatures and return shapes.

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

## Client Lifecycle

`YtMeta` owns an HTTP session (and a SQLite connection when `cache_path` is set). Use it as a context manager, or call `close()` when done:

```python
from yt_meta import YtMeta

with YtMeta(cache_path=".cache/yt.db") as client:
    meta = client.get_video_metadata("dQw4w9WgXcQ")
```

Short scripts can skip this; the OS reclaims everything at exit. Long-running processes should close the client, and on Windows an open SQLite cache file stays locked until closed.

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

> **Streams live on a separate tab.** Live, upcoming, and past live streams are on the channel's **Live (`/streams`) tab**, which `get_channel_videos` does not include. Use `get_channel_streams(channel_url)` for those; it yields the same item shape, with `is_upcoming` and `scheduled_text` on scheduled items.

### 6. Get Video Comments

Fetches comments for a given video, sorted by **"Most Recent"** (`sort_by='recent'`, the default) or **"Top comments"** (`sort_by='top'`). Returns a generator yielding standardized comment data.

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

Caching avoids re-fetching data from YouTube.

### Caching Is Off by Default

`YtMeta()` does not cache anything by default; every call hits the network. To enable caching, pass `cache=` (any dict-like object) or `cache_path=` (the built-in SQLite cache):

```python
from yt_meta import YtMeta

# In-memory cache: lasts for the lifetime of the client instance.
client = YtMeta(cache={})
# First call fetches from the network.
meta1 = client.get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
# Second call is served from the cache.
meta2 = client.get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
```

Enable caching if you call the same endpoints repeatedly (loops, notebooks, retries).

### Persistent Caching

To cache results across runs, pass a persistent dictionary-like object to the client. The library provides an optional `diskcache` integration.

Install the optional extra:
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

Any object implementing the `MutableMapping` protocol (e.g., `__getitem__`, `__setitem__`, `__delitem__`) works as a cache via the `cache=` kwarg: a plain `dict` for in-memory, `diskcache.Cache` for disk-backed, or `sqlitedict.SqliteDict` if you install sqlitedict yourself. See `examples/features/19_alternative_caching_sqlite.py` for the built-in SQLite path via `cache_path=`.

## Workflow Helpers

Three helpers cover common multi-step workflows (added in 0.8.0).

### Incremental Sync: `iter_new_videos`

Yields a channel's videos newest-first and stops before `since_video_id`, so you get only the videos published since your last run. Pagination also stops at the marker, keeping request cost proportional to the number of new videos. The first yielded video's id is the new high-water mark.

```python
from yt_meta import YtMeta

client = YtMeta()
last_seen_id = "pRiu3lxPZAw"  # saved from a previous run

new = list(client.iter_new_videos(
    "https://www.youtube.com/@TED",
    since_video_id=last_seen_id,
    max_videos=50,  # safety cap in case the marker is gone
))
if new:
    last_seen_id = new[0]["video_id"]  # persist for the next run
print(f"{len(new)} new videos")
```

### Exact Date Windows: `get_videos_published_between`

Returns videos published in an exact window, including hour-level `datetime` bounds. It binary-searches the chronological listing with probe fetches (about 2·log₂(n) requests) instead of fetching full metadata for every video near the window, which for a year-old target on a daily channel would be several hundred requests. Yielded videos carry full metadata with `publish_date_precision == "exact"`.

```python
from datetime import date, timedelta

from yt_meta import YtMeta

client = YtMeta()
videos = client.get_videos_published_between(
    "https://www.youtube.com/@TED",
    start_date=date.today() - timedelta(days=7),
    end_date=date.today(),
)
for v in videos:
    print(v["publish_date"], v["title"])
```

Bounds may also be `datetime` values for hour-level windows, e.g. `start_date=datetime(2023, 7, 5, 7, 30)`.

### Comment Hierarchies: `get_comment_threads`

Yields `(comment, replies)` tuples, wrapping `get_video_comments_with_reply_tokens` and `get_comment_replies`. `replies_per_thread` caps the replies fetched per thread; `0` skips reply fetching.

```python
from yt_meta import YtMeta

client = YtMeta()
video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

for comment, replies in client.get_comment_threads(
    video_url, limit=5, replies_per_thread=3
):
    print(comment["author"], f"({comment['reply_count']} replies)")
    for r in replies:
        print("  reply:", r["author"])
```

## Advanced Features

### Filtering Videos, Shorts, and Comments

The `filters` argument on `get_channel_videos`, `get_channel_shorts`, and `get_video_comments` selects items matching specific criteria.

#### Filter Validation
`yt-meta` validates your `filters` dictionary *before* making any network requests. If you provide a nonexistent field, an invalid operator, or an incorrect value type, the library raises a `ValueError` or `TypeError`.

Typos fail immediately instead of after a slow query. See `examples/features/23_filter_validation.py` for a demonstration.

#### Two-Stage Filtering: Fast vs. Slow

Filtering for videos and shorts runs in two stages:

*   **Fast filters** use metadata already present on the listing page (e.g. `title`, `view_count`) and cost no extra requests.
*   **Slow filters** need full metadata, fetched with one extra request per item, and run only on items that passed the fast filters.

The client automatically detects when a slow filter is used and sets `fetch_full_metadata=True` for you.

> [!NOTE]
> Comment filtering does not use the fast/slow system. All comment filters apply after fetching comment data.

#### Approximate vs. Exact Publish Dates

Every dated record carries two provenance fields alongside `publish_date`:

- `publish_date_precision`: `"exact"` (the watch page's `microformat.publishDate`; a timezone-aware upload timestamp) or `"approximate"` (parsed from the listing's relative text, i.e. query time minus "2 years ago").
- `publish_date_text`: the raw string YouTube displayed (`"3 years ago"`, `"Streamed 2 days ago"`; comments keep `"(edited)"` markers). Kept after `fetch_full_metadata=True` replaces the date with the exact one.

The time-of-day on an approximate date is meaningless, and its rounding error grows with age, up to about six months at year granularity. Approximate datetimes are also timezone-naive, so do not subtract one from an exact (timezone-aware) date. Comment dates are always approximate; relative text is all YouTube serves for them.

Filtering rules:

- `datetime` bounds (hour-level) on `publish_date` require `fetch_full_metadata=True` and compare against exact dates, with naive bounds matching wall-clock time. Without full metadata they raise `ValueError`.
- Bare `date` bounds compare calendar days everywhere.
- With full metadata enabled, approximate dates act only as a coarse pre-filter, padded by their own rounding error, and the exact date decides membership. The pagination early-stop is padded the same way, so videos near the window boundary are not dropped before their exact date is known.

#### Missing-field semantics

A filter on a field that is missing or `None` for a video drops that video; it cannot match. This is usually what you want (`publish_date >= 2023` should not include videos with no publish date), but it can surprise. Enable `logging.DEBUG` on the `yt_meta.filtering` logger to see each drop with the video id and the missing field. See M6 in the v0.6.0 CHANGELOG.

#### Supported Fields and Operators

The following table lists supported fields and their valid operators. Validation enforces these rules.

| Field                 | Supported Operators              | Content Type(s)                                             | Filter Speed |
| :-------------------- | :------------------------------- | :---------------------------------------------------------- | :----------- |
| `title`               | `contains`, `re`, `eq`           | Video, Short                                                | Fast         |
| `view_count`          | `gt`, `gte`, `lt`, `lte`, `eq`   | Video, Short                                                | Fast         |
| `duration_seconds`    | `gt`, `gte`, `lt`, `lte`, `eq`   | Video, Short                                                | Fast         |
| `publish_date`        | `gt`, `gte`, `lt`, `lte`, `eq`   | Video, Short, Comment                                       | Fast (Video, Playlist), **Slow** (Short) |
| `like_count`          | `gt`, `gte`, `lt`, `lte`, `eq`   | Video, Short, Comment                                       | **Slow**     |
| `category`            | `contains`, `re`, `eq`           | Video, Short                                                | **Slow**     |
| `keywords`            | `contains_any`, `contains_all` | Video, Short                                                | **Slow**     |
| `full_description`    | `contains`, `re`, `eq`           | Video                                                       | **Slow**     |
| `text`                | `contains`, `re`, `eq`           | Comment                                                     | N/A          |
| `author`              | `contains`, `re`, `eq`           | Comment                                                     | N/A          |
| `author_channel_id`   | `contains`, `re`, `eq`           | Comment                                                     | N/A          |
| `reply_count`         | `gt`, `gte`, `lt`, `lte`, `eq`   | Comment                                                     | N/A          |
| `is_creator`          | `eq`                             | Comment                                                     | N/A          |
| `is_reply`            | `eq`                             | Comment                                                     | N/A          |
| `is_hearted`          | `eq`                             | Comment                                                     | N/A          |
| `is_pinned`           | `eq`                             | Comment                                                     | N/A          |

> [!NOTE]
> `publish_date` is fast for channel videos and playlists but slow for shorts, whose listing pages carry no date. Fast dates are approximate (parsed from the listing's relative text); pass `fetch_full_metadata=True` when you need precision.

> [!NOTE]
> Comment filter keys were renamed in 0.8.0 to match the keys on the comment dicts: `channel_id` → `author_channel_id`, `is_by_owner` → `is_creator`, `is_hearted_by_owner` → `is_hearted`. The old names matched nothing and returned zero comments. `is_pinned` is new. `description_snippet` was removed; use `full_description` (slow) instead.

#### Example: Basic Filtering (Fast)

Both `view_count` and `duration_seconds` are fast filters, so this query needs no per-video requests.

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
> Playlists may not be chronological, so date filters scan the whole playlist; there is no early-stop as with channel videos. The date comes from the listing's relative text, with no per-video fetch unless you pass `fetch_full_metadata=True`. If a listing item lacks a date, the filter defers to that video's full metadata automatically.

> **Important Note on Shorts Filtering:**
> The Shorts feed provides no publish date on its fast path, so any date filter on `get_channel_shorts` triggers the full metadata fetch for each short.

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
-   **`accept_cookies`**: Opt in to bypassing YouTube's EU cookie-consent wall. Default `False` (no consent cookie is set). If a call fails with a `302` redirect to `consent.youtube.com` (region-gated, e.g. the EU), construct the client with `YtMeta(accept_cookies=True)`; a `SOCS` consent cookie is then set on the session so YouTube serves content directly. It is opt-in because it accepts YouTube's cookies on your behalf.

#### `get_video_metadata(youtube_url, *, video_id=None, force_refresh=False) -> dict | None`
Fetches metadata for a single YouTube video.
-   **`youtube_url`** / **`video_id`**: The video URL or a bare id (either keyword works).
-   **`force_refresh`**: Re-fetch even on a cache hit; use it to re-check a video's availability and pick up status changes.
-   **Returns**: A dictionary containing `title`, `view_count`, `like_count`, `publish_date` (a timezone-aware `datetime`, `publish_date_precision == "exact"`), `category`, etc., **plus video-status lifecycle fields** (see below). Returns `None` only when the page yields no player response at all.
-   **Raises**: `VideoUnavailableError` if the HTTP fetch itself fails (network error, 404, rate-limit). A video that is *parsed but unavailable* is reported via the `status` field, not an exception.

**Video status fields** (on every returned dict):

| Field | Meaning |
| --- | --- |
| `status` | `"ok"`, `"upcoming"` (scheduled premiere / live event not started), or `"unavailable"`. |
| `status_reason` | YouTube's reason text when not `ok` (e.g. `"Video unavailable"`, `"This live event will begin in 2 days."`), else `None`. |
| `status_checked_at` | ISO-8601 UTC time of the last availability check. |
| `status_changed_at` | ISO-8601 UTC time the status last changed (first sighting == `status_checked_at`). |
| `is_live` | `True` only while *currently* streaming. |
| `is_upcoming` | `True` for a scheduled premiere / live event not started. |
| `scheduled_start_time` | ISO-8601 start time for an upcoming stream, else `None`. |

URLs accepted everywhere include the `/live/<id>` form (with optional `?si=` share param) used for live streams and premieres.

When a previously-`ok` video is found `unavailable` (e.g. deleted), the result keeps the last-known-good content fields (title, channel, counts) and overlays the status fields, so prior data is not lost. Combine with `force_refresh=True` and a persistent cache to track a video's lifecycle.

#### `get_video_comments(youtube_url: str, limit: int | None = 100, sort_by: str = 'recent', progress_callback=None, since_date=None, filters: dict | None = None) -> Generator[dict, None, None]`
Fetches comments for a specific YouTube video.
-   **`youtube_url`**: The full URL of the YouTube video (any of `watch?v=...`, `youtu.be/...`, `/shorts/...`, or a bare 11-char id).
-   **`limit`**: Max comments to fetch. Defaults to `100`. Pass `None` or `-1` for unbounded; `since_date` is then required, to cap the request count on popular videos.
-   **`sort_by`**: `'recent'` (default; chronological, required for the `since_date` short-circuit) or `'top'` (YouTube's ranking).
-   **`since_date`**: A `date`, `datetime`, or `'YYYY-MM-DD'` string. The only filter that short-circuits pagination: with `sort_by='recent'`, fetching stops at the first comment older than the cutoff.
-   **`filters`**: Comment-level predicates applied after fetch (see the filter table above). They filter the fetched comments in memory and do not reduce request count. Use `since_date` for that.
-   **Returns**: A generator that yields a standardized dictionary for each comment.

#### `get_channel_metadata(channel_url: str) -> dict`
Fetches metadata for a specific channel. The client caches results.
-   **`channel_url`**: The URL of the channel.
-   **Returns**: A dictionary with channel metadata: `title`, `description`, `channel_id`, `vanity_url`, `keywords`, `is_family_safe`.
-   **Raises**: `VideoUnavailableError`, `MetadataParsingError`.

#### `get_channel_streams(channel_url, ..., fetch_full_metadata=False, stop_at_video_id=None, max_videos=-1) -> Generator[dict, None, None]`
Yields items from a channel's Live (`/streams`) tab: live, upcoming/scheduled, and past live streams. This tab is separate from Videos, so `get_channel_videos` does not include streams. Items use the same shape as `get_channel_videos`; upcoming streams carry `is_upcoming=True` and `scheduled_text` (the listing's "Scheduled for …"). Pass `fetch_full_metadata=True` for the precise `scheduled_start_time` and `status` per stream.

#### `get_video_comments_with_reply_tokens(youtube_url, ..., sort_by='recent', since_date=None, filters=None) -> Generator[dict, None, None]`
Like `get_video_comments`, but each comment that has replies also carries a `reply_continuation_token` you can pass to `get_comment_replies`.

#### `get_comment_replies(youtube_url, reply_continuation_token, limit=100, *, video_id=None) -> Generator[dict, None, None]`
Yields the replies for a single comment thread, identified by a `reply_continuation_token` obtained from `get_video_comments_with_reply_tokens`.

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

#### `get_channel_shorts(channel_url, ..., fetch_full_metadata=False, filters=None, max_videos=-1) -> Generator[dict, None, None]`
Yields items from a channel's **Shorts** tab. The fast path carries `title`/`view_count`; pass `fetch_full_metadata=True` for the rest (including `publish_date`).

#### `get_playlist_metadata(playlist_id) -> dict`
Fetches a playlist's own metadata (`title`, `author`, `description`, `video_count`, ...), not its videos.

#### `get_video_transcript(video_id, languages=None) -> list[dict]`
Fetches the transcript as `{text, start, duration}` snippets. Returns `[]` only when the video has no transcript (none in the requested languages, transcripts disabled, or video unavailable). Other failures, such as rate limiting or network errors, raise.

#### `iter_new_videos(channel_url, since_video_id=None, ...) -> Generator[dict, None, None]`
Incremental sync: everything newer than `since_video_id`, newest first, marker excluded. See [Workflow Helpers](#workflow-helpers).

#### `get_videos_published_between(channel_url, start_date, end_date=None) -> Generator[dict, None, None]`
Exact date/hour windows with ~2·log₂(n) probe hydrations. See [Workflow Helpers](#workflow-helpers).

#### `get_comment_threads(youtube_url, *, limit=20, replies_per_thread=10, sort_by='top') -> Generator[tuple[dict, list], None, None]`
`(comment, replies)` tuples. See [Workflow Helpers](#workflow-helpers).

#### `clear_cache(prefix=None)`
Clears the configured cache. Pass `prefix` (e.g. `"video_meta:"`) to clear only matching keys, for example to force fresh video metadata while keeping cached channel pages.

#### `close()`
Releases the HTTP session and (if `cache_path` was used) the SQLite connection. Idempotent; called automatically when using `with YtMeta() as client:`.

## Error Handling

The library uses custom exceptions to signal specific error conditions. All are importable from the top level (`from yt_meta import YtMetaError, VideoUnavailableError, MetadataParsingError`).

### `YtMetaError`
The base exception for all errors in this library:

```python
from yt_meta import YtMeta, YtMetaError

try:
    meta = YtMeta().get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    print(meta["title"], meta["status"])
except YtMetaError as e:
    print(f"yt-meta failed: {e}")
```

### `VideoUnavailableError`
Raised when an HTTP fetch itself fails: a network error, a 404, or a rate-limit response. A video that is fetched but unavailable (deleted, members-only, etc.) is not an exception; it is reported via the `status` field on `get_video_metadata`'s result.

### `MetadataParsingError`
Raised when a page is fetched successfully but the expected structure (e.g. `ytInitialData` or a channel tab) cannot be extracted. Usually a sign YouTube changed its page structure; see the next section.

### Builtin `ValueError` / `TypeError` for input mistakes

Invalid inputs raise builtin exceptions, not `YtMetaError`: a URL on a non-YouTube host, a malformed video id, an unknown filter key or operator, hour-level date bounds without `fetch_full_metadata=True`, or date kwargs mixed with time-bearing filter bounds. These are bugs in the calling code and surface immediately, unwrapped.

## When YouTube Changes Its Page Structure

This library parses YouTube's web pages, and YouTube periodically changes their structure. The most recent change (`videoRenderer` to `lockupViewModel`) broke the channel Videos tab, fixed in 0.6.0, and the playlist page, fixed in 0.7.1.

The symptom: requests succeed (HTTP 200, pagination runs) but a listing yields zero items, or `MetadataParsingError` is raised. Transient failures look different: the built-in retry (exponential backoff on 429/5xx, honoring `Retry-After`) absorbs those, so persistent zero results usually mean a structure change rather than throttling.

What to do:

1. Upgrade: `pip install -U yt-meta`. Structure changes are usually fixed within a release or two; see the CHANGELOG.
2. Confirm: run the live contract suite with `pytest -m contract` (or `make drift`). It asserts the page shapes this library depends on and reports which one moved. The offline test suite cannot catch this; it runs against captured fixtures, which stay green while the live site changes.
3. Report: open an issue with the failing contract-test output.

For maintainers: `docs/reviews/` holds the code-review history behind the `H*/M*/C*/R*` markers in code comments and test names, and `TESTING.md` documents the testing rules (captured fixtures, contract tests) that address this failure mode.