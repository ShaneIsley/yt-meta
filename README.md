# yt-meta

A Python library for reading metadata about YouTube videos, channels, playlists, comments and transcripts. It fetches YouTube's public web pages, parses them, and follows pagination for you. No API key is needed.

## Installation

```bash
pip install yt-meta
```

or, with uv:

```bash
uv pip install yt-meta
```

The package ships type annotations (`py.typed`), so IDEs and type checkers see the signatures.

## Quick start

```python
import itertools

from yt_meta import YtMeta

with YtMeta() as client:
    video = client.get_video_metadata("https://www.youtube.com/watch?v=B68agR-OeJM")
    print(video["title"], video["view_count"])

    for v in itertools.islice(client.get_channel_videos("https://www.youtube.com/@ArjanCodes"), 3):
        print(v["publish_date_text"], v["title"])
```

`YtMeta` owns an HTTP session, and a SQLite connection when `cache_path` is set. Use it as a context manager or call `close()` when you're done. Short scripts can skip this, since everything is released at exit. Long-running processes should close the client, and on Windows an open SQLite cache file stays locked until it is closed. The remaining examples omit `close()` for brevity.

Listing and comment methods return generators: nothing is fetched until you iterate, and pages are requested as you go. Arguments are checked when you call the method, so a mistake raises on that line.

## Usage

### Video metadata

```python
from yt_meta import YtMeta

client = YtMeta()
video = client.get_video_metadata("https://www.youtube.com/watch?v=B68agR-OeJM")
print(video["title"], video["publish_date"], video["status"])
```

Any URL form works: `watch?v=`, `youtu.be/`, `/shorts/`, `/live/` (with or without a `?si=` share parameter), or a bare 11-character id. Every result carries status fields (`status`, `status_reason`, `status_checked_at`, `status_changed_at`); see [`get_video_metadata`](#get_video_metadatayoutube_url--video_idnone-force_refreshfalse) for what they mean.

### Channel metadata

```python
from yt_meta import YtMeta

client = YtMeta()
channel = client.get_channel_metadata("https://www.youtube.com/@samwitteveenai")
print(channel["title"], channel["channel_id"])
```

### Channel videos

`get_channel_videos` yields the channel's Videos tab, newest first, following pagination.

```python
import itertools

from yt_meta import YtMeta

client = YtMeta()
for video in itertools.islice(client.get_channel_videos("https://www.youtube.com/@AI-Makerspace"), 5):
    print(f"- {video['title']} ({video['video_id']})")
```

Live, upcoming and past live streams are on a separate tab and are not included; use [`get_channel_streams`](#live-streams).

### Shorts

`get_channel_shorts` yields the Shorts tab. The listing carries only `title` and `view_count`; pass `fetch_full_metadata=True` for everything else, at one extra request per Short.

```python
import itertools

from yt_meta import YtMeta

client = YtMeta()
shorts = client.get_channel_shorts("https://www.youtube.com/@bashbunni", fetch_full_metadata=True)
for short in itertools.islice(shorts, 3):
    print(f"- {short['title']} ({short['like_count']} likes, {short['publish_date']:%Y-%m-%d})")
```

### Live streams

`get_channel_streams` yields the channel's Live (`/streams`) tab: live, upcoming and past streams. Items have the same shape as channel videos. Upcoming streams have `is_upcoming=True` and `scheduled_text` (the listing's "Scheduled for …" text); pass `fetch_full_metadata=True` for the exact `scheduled_start_time` and `status`.

```python
import itertools

from yt_meta import YtMeta

client = YtMeta()
for stream in itertools.islice(client.get_channel_streams("https://www.youtube.com/@AppleDeveloper"), 3):
    print(stream["title"], stream["is_upcoming"], stream["publish_date_text"] or stream["scheduled_text"])
```

### Playlists

```python
import itertools

from yt_meta import YtMeta

client = YtMeta()
playlist_id = "PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"
print(client.get_playlist_metadata(playlist_id)["title"])
for video in itertools.islice(client.get_playlist_videos(playlist_id), 5):
    print(f"- {video['title']} ({video['video_id']})")
```

### Comments

`get_video_comments` yields top-level comments. `sort_by='recent'` (the default for every comment method) is chronological, which `since_date` relies on. It is YouTube's "Newest" view, which YouTube says can include spam. `sort_by='top'` is YouTube's ranked view, the one the site shows by default.

```python
from yt_meta import YtMeta

client = YtMeta()
for comment in client.get_video_comments("https://www.youtube.com/watch?v=B68agR-OeJM", limit=5):
    print(f"- {comment['author']}: {comment['text'][:80]} ({comment['like_count']} likes)")
```

Pass `since_date` to get only comments posted on or after a date. Fetching stops at the first comment older than the cutoff, so it also limits the number of requests. Pinned comments are skipped by that check, since YouTube pins them to the top regardless of age.

```python
from datetime import date, timedelta

from yt_meta import YtMeta

client = YtMeta()
comments = client.get_video_comments(
    "https://www.youtube.com/watch?v=B68agR-OeJM",
    since_date=date.today() - timedelta(days=30),
    limit=None,  # unbounded is allowed because since_date caps the fetch
)
for comment in comments:
    print(f"- {comment['publish_date']}: {comment['text'][:80]}")
```

Comment dates are always approximate: YouTube only shows relative text ("3 days ago") for them.

#### Replies

`get_comment_threads` yields `(comment, replies)` pairs. `replies_per_thread` caps the replies fetched per thread; `0` skips reply requests. YouTube's reply count can be higher than the replies it serves (it counts held or removed replies), so treat `reply_count` as an upper bound.

```python
from yt_meta import YtMeta

client = YtMeta()
for comment, replies in client.get_comment_threads(
    "https://www.youtube.com/watch?v=B68agR-OeJM", limit=5, replies_per_thread=3
):
    print(comment["author"], f"({comment['reply_count']} replies)")
    for reply in replies:
        print("  reply:", reply["author"])
```

For manual control, `get_video_comments_with_reply_tokens` adds a `reply_continuation_token` to each comment that has replies, and `get_comment_replies` fetches them.

### Transcripts

`get_video_transcript` returns `{text, start, duration}` snippets in the first available language from `languages` (default `["en"]`). It returns `[]` when the video has no transcript in those languages; other failures, such as rate limiting, raise.

```python
from yt_meta import YtMeta

client = YtMeta()
transcript = client.get_video_transcript("dQw4w9WgXcQ", languages=["es", "en"])
for snippet in transcript[:5]:
    print(f"[{snippet['start']:.2f}s] {snippet['text'].replace(chr(10), ' ')}")
```

### New videos since the last run

`iter_new_videos` yields a channel's videos newest first and stops before `since_video_id`, the newest id you saw last time. Pagination stops at the marker too, so the cost is proportional to the number of new videos. Save the first yielded id for the next run.

```python
from yt_meta import YtMeta

client = YtMeta()
last_seen_id = "pRiu3lxPZAw"  # saved from a previous run

new = list(client.iter_new_videos(
    "https://www.youtube.com/@ArjanCodes",
    since_video_id=last_seen_id,
    max_videos=50,  # safety cap in case the marker video was deleted
))
if new:
    last_seen_id = new[0]["video_id"]
print(f"{len(new)} new videos")
```

### Videos published in an exact window

`get_videos_published_between` returns the videos published in a date or hour window, with exact dates. A plain date filter with `fetch_full_metadata=True` would fetch every video near the window, which can be hundreds of requests on a busy channel. This method binary-searches the listing instead, at about 2·log₂(n) full-metadata requests, then fetches only the videos inside the window.

```python
from datetime import date, timedelta

from yt_meta import YtMeta

client = YtMeta()
videos = client.get_videos_published_between(
    "https://www.youtube.com/@ArjanCodes",
    start_date=date.today() - timedelta(days=30),
    end_date=date.today(),
)
for v in videos:
    print(v["publish_date"], v["title"])
```

Bounds may be `datetime` values for hour-level windows, for example `start_date=datetime(2026, 7, 5, 7, 30)`.

## Filtering

`filters` selects items by field. Video filters work on `get_channel_videos`, `get_channel_shorts`, `get_channel_streams` and `get_playlist_videos`. Comment filters work on `get_video_comments`, `get_video_comments_with_reply_tokens` and `get_comment_threads`. Each field maps to a dictionary of operator and value:

```python
import itertools

from yt_meta import YtMeta

client = YtMeta()
filters = {
    "view_count": {"gt": 20_000},
    "duration_seconds": {"lt": 15 * 60},
}
videos = client.get_channel_videos("https://www.youtube.com/@ArjanCodes", filters=filters)
for video in itertools.islice(videos, 5):
    print(f"- {video['title']} ({video['view_count']:,} views, {video['duration_seconds']}s)")
```

### Fields and operators

| Field | Operators | Applies to | Speed |
| :-- | :-- | :-- | :-- |
| `title` | `contains`, `re`, `eq` | Video, Short | Fast |
| `view_count` | `gt`, `gte`, `lt`, `lte`, `eq` | Video, Short | Fast |
| `duration_seconds` | `gt`, `gte`, `lt`, `lte`, `eq` | Video, Short | Fast for videos, slow for Shorts |
| `publish_date` | `gt`, `gte`, `lt`, `lte`, `eq`, `after`, `before` | Video, Short, Comment | Fast for videos and playlists, slow for Shorts |
| `like_count` | `gt`, `gte`, `lt`, `lte`, `eq` | Video, Short, Comment | Slow |
| `category` | `contains`, `re`, `eq` | Video, Short | Slow |
| `keywords` | `contains_any`, `contains_all` | Video, Short | Slow |
| `full_description` | `contains`, `re`, `eq` | Video | Slow |
| `text` | `contains`, `re`, `eq` | Comment | |
| `author` | `contains`, `re`, `eq` | Comment | |
| `author_channel_id` | `contains`, `re`, `eq` | Comment | |
| `reply_count` | `gt`, `gte`, `lt`, `lte`, `eq` | Comment | |
| `is_creator`, `is_reply`, `is_hearted`, `is_pinned` | `eq` | Comment | |

Fast filters use what the listing page already shows and cost nothing extra. Slow filters need each item's full metadata, one extra request per item, and run only on items that passed the fast filters. Using a slow filter turns on `fetch_full_metadata` automatically. Comment filters run on the fetched comments and never cost extra requests; use `since_date` to limit how many are fetched.

Filters are checked when you call the method, before any request. An unknown field or operator, or a field that doesn't exist on that kind of record (such as `is_reply` on `get_channel_videos`), raises `ValueError`. A value of the wrong type for its field (such as `{"view_count": {"eq": "100"}}`) raises `TypeError`. See `examples/features/23_filter_validation.py`.

### Dates

The simplest date filter is `start_date` and `end_date`. They accept `date` objects, `"YYYY-MM-DD"` strings and relative strings such as `"30d"` or `"6 months ago"`. On channel videos, pagination stops once the listing passes `start_date`.

```python
import itertools

from yt_meta import YtMeta

client = YtMeta()
videos = client.get_channel_videos("https://www.youtube.com/@samwitteveenai", start_date="6 months ago")
for video in itertools.islice(videos, 5):
    print(f"- {video['title']} ({video['publish_date_text']})")
```

A `publish_date` condition in `filters` does the same with any operator; `start_date` and `end_date`, when given, replace the bound on their side.

Each dated record says how precise its date is:

- `publish_date_precision` is `"exact"` when the date comes from the video's own page (a timezone-aware upload time), or `"approximate"` when it was parsed from relative listing text ("2 years ago").
- `publish_date_text` is the relative text the date came from. For listings it is the long form YouTube gives screen readers (`"11 days ago"`, `"Streamed 3 weeks ago"`), not the compact text the page shows (`"11d ago"`). Comments keep YouTube's text, including `"(edited)"`. It is kept when `fetch_full_metadata=True` replaces the date with the exact one.

An approximate date's time of day is meaningless, and its error grows with age, up to about six months for "N years ago". Approximate datetimes have no timezone, so don't subtract one from an exact, timezone-aware date.

The rules:

- `date` bounds compare calendar days.
- `datetime` bounds compare exact times and need `fetch_full_metadata=True`; without it they raise `ValueError`. A bound without a timezone is compared with the video's local wall-clock time.
- With `fetch_full_metadata=True`, approximate dates are only a pre-filter, widened by their possible error, and the exact date decides. Pagination stops with the same allowance, so videos near the edge of the window are not missed.
- Playlists may not be in date order, so date filters scan the whole playlist. An item whose listing has no date is dropped, unless you pass `fetch_full_metadata=True`, in which case its exact date is checked instead.
- The Shorts listing has no dates, so any date filter on `get_channel_shorts` fetches full metadata for each Short.

### Missing fields

A filter on a field that is missing or `None` for an item drops that item. `publish_date >= 2023` should not include videos with no date, but it can be surprising. Set the `yt_meta.filtering` logger to `DEBUG` to see each dropped item with its id and the missing field.

### Renamed comment fields

0.8.0 renamed comment filter fields to match the keys on comment records: `channel_id` became `author_channel_id`, `is_by_owner` became `is_creator`, and `is_hearted_by_owner` became `is_hearted`. The old names raise `ValueError` with the new name. `description_snippet` was removed; use `full_description` (slow) instead.

## Caching

`YtMeta()` caches nothing by default: every call goes to YouTube. Turn caching on when you request the same things repeatedly, in loops, notebooks or scheduled jobs.

| Option | How | Lasts | Notes |
| :-- | :-- | :-- | :-- |
| In memory | `YtMeta(cache={})` | The client's lifetime | Any `dict` works. |
| Built-in SQLite (recommended for persistence) | `YtMeta(cache_path="cache/yt.db")` | Until the entry's TTL expires (`cache_ttl_seconds`, default one day) | Stored as JSON. Safe to share between threads. |
| Your own store | `YtMeta(cache=obj)` | Up to `obj` | Any `MutableMapping`, such as `diskcache.Cache` or `sqlitedict.SqliteDict`. |

```python
from yt_meta import YtMeta

with YtMeta(cache_path=".cache/yt.db") as client:
    client.get_video_metadata("dQw4w9WgXcQ")  # fetched from YouTube
    client.get_video_metadata("dQw4w9WgXcQ")  # read from the cache
```

Pass `force_refresh=True` to a method to skip the cache for that call, for example to re-check whether a video is still available. `clear_cache()` empties the cache; `clear_cache(prefix="video_meta:")` removes only cached video metadata.

To use `diskcache`, install the extra and pass a `Cache`. It stores values with pickle, so keep its directory private:

```bash
pip install "yt-meta[persistent_cache]"
```

```python
from diskcache import Cache

from yt_meta import YtMeta

client = YtMeta(cache=Cache(".my_yt_meta_cache"))
client.get_video_metadata("dQw4w9WgXcQ")
```

## Logging

yt-meta logs through Python's `logging` module under the `yt_meta` logger: requests at `INFO`, recoverable problems (a skipped video, an unparseable comment date, a fallback sort order) at `WARNING`.

```python
import logging

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("yt_meta.filtering").setLevel(logging.DEBUG)  # see why items were filtered out
```

## Errors

All library errors subclass `YtMetaError` and are importable from `yt_meta`.

```python
from yt_meta import YtMeta, YtMetaError

try:
    video = YtMeta().get_video_metadata("https://www.youtube.com/watch?v=B68agR-OeJM")
    print(video["title"], video["status"])
except YtMetaError as e:
    print(f"yt-meta failed: {e}")
```

`VideoUnavailableError` means a request failed: a network error, or an HTTP error status (404, or 429/5xx after retries). A video that is private, deleted or members-only is not an error; `get_video_metadata` returns it with `status="unavailable"`.

The same rule applies to every listing. If its first page can't be fetched, iterating it raises `VideoUnavailableError`, so a missing channel is not mistaken for an empty one. If a later page fails, the error is raised mid-iteration and the items already yielded are still valid. With `fetch_full_metadata=True`, a single video whose page fails is logged and skipped.

`MetadataParsingError` means a page was fetched but its data could not be read, usually because YouTube changed the page (see the next section). Comment fetching also raises it when the page has no API key (a consent page or a layout change), or when `since_date` is set but YouTube offers no newest-first ordering.

Mistakes in the call raise builtin `ValueError` or `TypeError` instead, when you call the method and before any request:

- a URL on a non-YouTube host, a malformed video id, or both or neither of `youtube_url` and `video_id`
- an unknown filter field or operator, a field that doesn't apply to the record kind, or a value of the wrong type
- an unknown `sort_by`, `since_date` with `sort_by='top'`, or `limit=None` without `since_date`
- `get_videos_published_between` without `start_date`
- `datetime` bounds without `fetch_full_metadata=True`, or `start_date`/`end_date` combined with a `publish_date` filter that has a time of day

Requests that fail with 429 or 5xx are retried with exponential backoff, honoring `Retry-After`.

## API reference

All methods are on `YtMeta`. Methods described as generators check their arguments when called; requests start on first iteration.

### `YtMeta(cache_path=None, cache=None, cache_ttl_seconds=86400, accept_cookies=False)`

- `cache_path`: path of a SQLite file for the built-in persistent cache. The client creates and manages it.
- `cache`: any `MutableMapping` to use as the cache. Takes precedence over `cache_path`. With neither, nothing is cached.
- `cache_ttl_seconds`: lifetime of built-in SQLite cache entries, in seconds. Ignored for `cache=`.
- `accept_cookies`: set YouTube's consent cookie so requests from regions with a cookie-consent page (such as the EU) aren't redirected to `consent.youtube.com`. Off by default because it accepts YouTube's cookies on your behalf. Turn it on if calls fail with a redirect to the consent page.

### `get_video_metadata(youtube_url, *, video_id=None, force_refresh=False)`

Returns a dict with `title`, `channel_name`, `channel_id`, `view_count`, `like_count`, `duration_seconds`, `publish_date` (exact, timezone-aware), `category`, `keywords`, `full_description`, `thumbnails` and more, or `None` if the page had no player data at all.

- `youtube_url` / `video_id`: the video, as any URL form or a bare id. Pass exactly one.
- `force_refresh`: skip the cache.

Status fields on every result:

| Field | Meaning |
| --- | --- |
| `status` | `"ok"`, `"upcoming"` (scheduled premiere or live event not started) or `"unavailable"`. |
| `status_reason` | YouTube's reason text when not `"ok"`, such as `"Video unavailable"`. |
| `status_checked_at` | ISO-8601 UTC time of this check. |
| `status_changed_at` | ISO-8601 UTC time the status last changed. Equal to `status_checked_at` on first sight. |
| `is_live` | `True` only while the video is streaming live. |
| `is_upcoming` | `True` for a scheduled premiere or live event that hasn't started. |
| `scheduled_start_time` | ISO-8601 start time of an upcoming stream, else `None`. |

When a cached video is found `"unavailable"` on a later check, the result keeps the cached title, channel and counts and updates only the status fields. Combine a persistent cache with `force_refresh=True` to track a video over time.

Raises `VideoUnavailableError` if the request fails.

### `get_channel_metadata(channel_url, force_refresh=False)`

Returns `title`, `description`, `channel_id`, `vanity_url`, `keywords` and `is_family_safe`. No subscriber or view counts.

- `channel_url`: the channel's home page or any of its tabs.
- `force_refresh`: skip the cache.

### `get_channel_videos(channel_url, force_refresh=False, fetch_full_metadata=False, start_date=None, end_date=None, filters=None, stop_at_video_id=None, max_videos=-1)`

Generator of the channel's Videos tab, newest first.

- `force_refresh`: skip the cache for the listing pages.
- `fetch_full_metadata`: fetch each video's page for the full fields and exact dates, one request per video. Turned on automatically by slow filters.
- `start_date`, `end_date`: date window; see [Dates](#dates).
- `filters`: see [Filtering](#filtering).
- `stop_at_video_id`: stop after this video, whether or not it passes the filters. It is yielded if it does.
- `max_videos`: stop after this many results; `-1` for no limit.

### `get_channel_shorts(channel_url, force_refresh=False, fetch_full_metadata=False, filters=None, stop_at_video_id=None, max_videos=-1)`

Generator of the channel's Shorts tab. The listing has `title` and `view_count`; everything else needs `fetch_full_metadata=True`. Other parameters as for `get_channel_videos`.

### `get_channel_streams(channel_url, force_refresh=False, fetch_full_metadata=False, filters=None, stop_at_video_id=None, max_videos=-1)`

Generator of the channel's Live tab. Items are shaped like channel videos, plus `is_upcoming` and `scheduled_text`. Other parameters as for `get_channel_videos`.

### `get_playlist_videos(playlist_id, fetch_full_metadata=False, start_date=None, end_date=None, filters=None, stop_at_video_id=None, max_videos=-1)`

Generator of a playlist's videos in playlist order. Parameters as for `get_channel_videos`; date filters scan the whole playlist.

### `get_playlist_metadata(playlist_id)`

Returns the playlist's `title`, `author`, `description`, `video_count` and `playlist_id`.

### `get_videos_published_between(channel_url, start_date, end_date=None, force_refresh=False)`

Generator of the channel's videos published in the window, newest first, each with full metadata and an exact date. `start_date` is required. `end_date=None` means up to the newest video. Bounds may be strings, dates or datetimes.

### `iter_new_videos(channel_url, since_video_id=None, fetch_full_metadata=False, force_refresh=False, max_videos=-1)`

Generator of the channel's videos newer than `since_video_id`, newest first, excluding the marker itself. With `since_video_id=None` it yields from the newest video; bound it with `max_videos`. A marker that no longer exists also yields everything, so set `max_videos` as a safety cap.

### `get_video_comments(youtube_url, limit=100, sort_by="recent", progress_callback=None, since_date=None, filters=None, *, video_id=None)`

Generator of top-level comments.

- `youtube_url` / `video_id`: the video. Pass exactly one.
- `limit`: maximum comments. `None` or `-1` for no limit, which requires `since_date`.
- `sort_by`: `"recent"` (newest first) or `"top"` (YouTube's ranking).
- `progress_callback`: called with the running count after each comment.
- `since_date`: only comments on or after this date (a `date`, `datetime`, `"YYYY-MM-DD"` or relative string). Requires `sort_by="recent"`. Fetching stops at the first older comment.
- `filters`: comment filters; see [Filtering](#filtering).

### `get_video_comments_with_reply_tokens(youtube_url, limit=100, sort_by="recent", progress_callback=None, since_date=None, filters=None, *, video_id=None)`

As `get_video_comments`, and each comment with replies also has a `reply_continuation_token` for `get_comment_replies`.

### `get_comment_replies(youtube_url, reply_continuation_token, limit=100, progress_callback=None, *, video_id=None)`

Generator of the replies in one thread, identified by a `reply_continuation_token`.

### `get_comment_threads(youtube_url, *, video_id=None, limit=20, replies_per_thread=10, sort_by="recent", since_date=None, filters=None)`

Generator of `(comment, replies)` pairs. `filters` apply to top-level comments only; `replies_per_thread=0` skips reply requests. Other parameters as for `get_video_comments`.

### `get_video_transcript(video_id, languages=None, *, youtube_url=None)`

Returns a list of `{text, start, duration}` snippets in the first available language from `languages` (default `["en"]`), or `[]` when there is none. Rate limiting and network errors raise.

### `clear_cache(prefix=None)`

Removes all cached entries, or only keys starting with `prefix`. Prefixes in use: `video_meta:`, `video_initial:`, `channel_page:`, `channel_shorts_page:`, `channel_streams_page:` and `continuation:`.

### `close()`

Closes the HTTP session and the built-in SQLite cache. Safe to call twice; called automatically by `with YtMeta() as client:`.

## When YouTube changes its pages

yt-meta reads YouTube's web pages, and YouTube changes them without notice. Recent examples: the channel Videos tab and playlists moved to a new item format (fixed in 0.6.0 and 0.7.1), and in 2026 listings switched to compact text and some pages to a new data layout (fixed in the next release).

The symptom is a listing that yields nothing, or a `MetadataParsingError`, while requests succeed. Rate limiting looks different: the built-in retry absorbs it.

1. Upgrade: `pip install -U yt-meta`. Fixes usually ship within a release or two; see the CHANGELOG.
2. Confirm: run the live suite with `pytest -m contract` (or `make drift`). It checks the page shapes this library depends on, and key behaviors against real channels, and reports what moved. The offline tests can't catch this, because they use saved pages.
3. Report: open an issue with the failing output.

## For maintainers

`YtMeta` is a thin facade over fetchers in `yt_meta/fetchers.py` (channel tabs, playlists, single videos), `yt_meta/comment_fetcher.py` and `yt_meta/transcript_fetcher.py`. Everything that knows YouTube's page layout is in `yt_meta/parsing.py`; the fetchers only request pages and follow next-page tokens. The error policy is written at the top of `yt_meta/fetchers.py`.

`TESTING.md` describes the testing rules. `docs/reviews/` holds the code reviews behind the `H*/M*/C*/R*` labels in code comments and test names.
