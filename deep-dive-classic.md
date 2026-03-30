# yt-meta: Facade Pattern as API Design Philosophy

*2026-03-30T00:34:23Z by Showboat 0.6.1*
<!-- showboat-id: 3f395557-8edd-4f36-b40b-d7439d5bdff5 -->

## What This Library Does — and Why the Interface Is the Product

**yt-meta** is a Python library published on PyPI for fetching YouTube metadata — videos, channels, playlists, comments, and transcripts — without requiring an API key. It scrapes YouTube's internal API surface, parses the nested JSON responses, and presents callers with clean Python dicts and generators.

Thirteen releases in, the hardest problem was never *getting* the data. YouTube's public pages hand you everything if you know where to look. The hard problem is **what the caller sees**: a stable, predictable interface that hides pagination quirks, inconsistent response shapes, and caching concerns behind a single import.

This walkthrough traces one architectural decision — the Facade pattern — from the public API surface down through the internals, and explains why each layer exists.

## The Facade: One Class, Five Specialists

The entire public API is a single class: `YtMeta`. A consumer instantiates it once, optionally with a cache path, and calls methods like `get_video_metadata()` or `get_channel_videos()`. They never import a fetcher, build a session, or think about pagination tokens.

Here's the constructor — the point where the Facade assembles its delegates:

```bash
sed -n '1,60p' yt_meta/client.py
```

```output
from .caching import DummyCache, SQLiteCache
from .fetchers import ChannelFetcher, PlaylistFetcher, VideoFetcher
from .comment_fetcher import CommentFetcher
from .transcript_fetcher import TranscriptFetcher

class YtMeta:
    """
    A client for fetching metadata for YouTube videos, channels, playlists, and comments.
    This class acts as a Facade, delegating calls to specialized fetcher classes.
    """

    def __init__(self, cache_path: str | None = None):
        self.session = Client(headers={"Accept-Language": "en-US,en;q=0.5"})
        if cache_path:
            self.cache = SQLiteCache(path=cache_path)
        else:
            self.cache = DummyCache()

        self._video_fetcher = VideoFetcher(session=self.session, cache=self.cache)
        self._channel_fetcher = ChannelFetcher(
            session=self.session, cache=self.cache, video_fetcher=self._video_fetcher
        )
        self._playlist_fetcher = PlaylistFetcher(
            session=self.session, cache=self.cache, video_fetcher=self._video_fetcher
        )
        self._comment_fetcher = CommentFetcher()
        self._transcript_fetcher = TranscriptFetcher()
```

Notice the branching on `cache_path`: callers get either a real `SQLiteCache` or a `DummyCache` (a no-op implementation of the same interface). The fetchers don't know or care which one they received — they just call `cache[key]`. This is the Strategy pattern nested inside the Facade, and it means every unit test can run with `YtMeta(cache_path=None)` and never touch disk.

Five fetchers, one shared HTTP session, one shared cache. The Facade wires them together and the caller sees ten clean methods:

```bash
grep -n 'def get_\|def clear_' yt_meta/client.py | head -20
```

```output
55:    def clear_cache(self, prefix: str | None = None):
69:    def get_channel_metadata(
84:    def get_video_metadata(self, youtube_url: str) -> dict:
96:    def get_video_transcript(
112:    def get_channel_videos(
158:    def get_playlist_videos(
198:    def get_channel_shorts(
230:    def get_video_comments(
265:    def get_video_comments_with_reply_tokens(
297:    def get_comment_replies(
```

Each method is a thin delegation. `get_video_metadata` calls `self._video_fetcher.get_video_metadata()`. `get_channel_videos` calls `self._channel_fetcher.get_channel_videos()`. The Facade adds just enough value at the boundary — date resolution, filter merging — to justify its existence without duplicating logic.

**Why not just expose the fetchers directly?** Two reasons. First, fetchers share infrastructure (session, cache) that callers shouldn't manage. Second, the Facade is a **versioning firewall**: internal class boundaries can shift between releases without breaking imports. The caller's contract is with `YtMeta`, not with `ChannelFetcher`.

## Deep Dive: The Channel Fetcher

The `ChannelFetcher` is the most complex fetcher and the best illustration of what each specialist handles. It manages three concerns: **page fetching with caching**, **pagination via continuation tokens**, and **a two-tier filtering system**.

```bash
sed -n '150,200p' yt_meta/fetchers.py
```

```output
class ChannelFetcher(_BaseFetcher):
    """Fetches data related to a YouTube channel's videos and shorts."""

    def _get_channel_page_cache_key(self, channel_url: str) -> str:
        key = channel_url.rstrip("/")
        if not key.endswith("/videos"):
            key += "/videos"
        return f"channel_page:{key}"

    def _get_channel_page_data(
        self, channel_url: str, force_refresh: bool = False
    ) -> tuple[dict, dict, str]:
        key = self._get_channel_page_cache_key(channel_url)
        if not force_refresh and key in self.cache:
            return self.cache[key]
        try:
            response = self.session.get(key.replace("channel_page:", ""), timeout=10)
            response.raise_for_status()
            html = response.text
        except httpx.RequestError as e:
            raise VideoUnavailableError(
                f"Could not fetch channel page: {e}", channel_url=key
            ) from e
        initial_data = parsing.extract_and_parse_json(html, "ytInitialData")
        ytcfg = parsing.find_ytcfg(html)
        # ... caches the tuple (initial_data, ytcfg, html) and returns it
```

The fetcher checks the cache first. On a miss, it fetches the HTML, extracts two embedded JSON blobs (`ytInitialData` and `ytcfg`), and caches the parsed tuple. The cache key is deterministic — normalized URL with a `channel_page:` prefix — so repeated calls for the same channel hit cache regardless of trailing slashes or path variations.

### Pagination: Generators All the Way Down

YouTube's channel pages return ~30 videos at a time with a continuation token for the next batch. Rather than eagerly fetching everything, the fetcher yields videos through a generator:

```bash
sed -n '283,335p' yt_meta/fetchers.py
```

```output
    def _get_raw_channel_videos_generator(
        self, channel_url, force_refresh, final_start_date
    ):
        try:
            initial_data, ytcfg, _ = self._get_channel_page_data(
                channel_url, force_refresh=force_refresh
            )
        except VideoUnavailableError as e:
            self.logger.error("Could not fetch initial channel page: %s", e)
            return
        if not initial_data:
            raise MetadataParsingError(
                "Could not find initial data script in channel page"
            )
        tab_renderer = self._get_videos_tab_renderer(initial_data)
        if not tab_renderer:
            raise MetadataParsingError(
                "Could not find videos tab renderer in channel page"
            )
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
                    if (
                        video_publish_date
                        and video_publish_date.date() < final_start_date
                    ):
                        stop_pagination = True
                yield video
            if stop_pagination or not continuation_token:
                break
            continuation_data = self._get_continuation_data(continuation_token, ytcfg)
            if not continuation_data:
                break
            continuation_token = self._get_continuation_token_from_data(
                continuation_data
            )
            renderers = self._get_video_renderers_from_data(continuation_data)

    def _get_raw_shorts_generator(self, channel_url, force_refresh):
        try:
            initial_data, ytcfg, _ = self._get_channel_shorts_page_data(
```

This is the pagination engine. It fetches the initial page, yields each video, then follows the continuation token for the next batch. Three details matter:

1. **Lazy evaluation.** The caller writes `for video in client.get_channel_videos(url)` and gets videos one at a time. A channel with 5,000 videos never loads them all into memory.
2. **Early termination.** The `final_start_date` check sets `stop_pagination = True` but still yields the current video — you get every video in the date window without wasting a network round-trip on the next page.
3. **Continuation caching.** Each continuation response is cached by its token. Re-running the same query hours later skips pages that were already fetched.

### Two-Tier Filtering

Not all metadata is available from the channel listing page. View counts and titles are — but like counts, categories, and full descriptions require a separate per-video fetch. The fetcher partitions filters into "fast" (available from listing data) and "slow" (require full metadata):

```bash
grep -n 'FAST_FILTER\|SLOW_FILTER\|fast_filters\|slow_filters\|_partition_filters' yt_meta/fetchers.py | head -15
```

```output
38:        fast_filters,
39:        slow_filters,
45:            if not apply_filters(video, fast_filters):
55:                        if slow_filters:
64:            if not apply_filters(merged_video, slow_filters):
443:        fast_filters, slow_filters = partition_filters(filters, content_type="videos")
444:        must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)
445:        if slow_filters and not fetch_full_metadata:
447:                f"Slow filters {list(slow_filters.keys())} provided without fetch_full_metadata=True. Full metadata will be fetched."
455:            fast_filters=fast_filters,
456:            slow_filters=slow_filters,
487:        fast_filters, slow_filters = partition_filters(filters, content_type="shorts")
488:        must_fetch_full_metadata = fetch_full_metadata or bool(slow_filters)
489:        if slow_filters and not fetch_full_metadata:
491:                f"Slow filters {list(slow_filters.keys())} provided without fetch_full_metadata=True. Full metadata will be fetched."
```

```bash
sed -n '52,78p' yt_meta/filtering.py
```

```output
def partition_filters(filters: dict, content_type: str) -> tuple[dict, dict]:
    """Partitions filters into fast and slow based on content type.
    Fast filters use data from the channel listing page.
    Slow filters require a full per-video metadata fetch."""
    if not filters:
        return {}, {}
    fast_filters = {}
    slow_filters = {}
    for key, value in filters.items():
        if content_type == "videos" and key in FAST_VIDEO_FILTERS:
            fast_filters[key] = value
        elif content_type == "shorts" and key in FAST_SHORTS_FILTERS:
            fast_filters[key] = value
        else:
            slow_filters[key] = value
    return fast_filters, slow_filters
```

This is a performance-aware design: fast filters run on every video at near-zero cost. Slow filters trigger an additional HTTP request per video. The fetcher auto-promotes to full-metadata mode when slow filters are present, with a log warning so the caller understands the cost.

## The Caching Layer: SQLiteCache and the Null Object

The caching design uses two patterns together: **MutableMapping protocol** (so the cache behaves like a dict) and the **Null Object pattern** (so disabling the cache requires zero conditionals in fetcher code).

```bash
cat yt_meta/caching.py
```

```output
class DummyCache(MutableMapping):
    """A dummy cache that stores nothing. Used when caching is disabled."""
    def __getitem__(self, key):  raise KeyError(key)
    def __setitem__(self, key, value):  pass
    def __delitem__(self, key):  pass
    def __iter__(self):  return iter([])
    def __len__(self):  return 0

class SQLiteCache(MutableMapping):
    def __init__(self, path=".my_yt_meta_cache/cache.db", ttl_seconds=86400):
        self.path = path
        self.ttl_seconds = ttl_seconds
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value BLOB, timestamp REAL)"
        )

    def __getitem__(self, key):
        cursor = self._conn.execute(
            "SELECT value, timestamp FROM cache WHERE key = ?", (key,)
        )
        result = cursor.fetchone()
        if result is None:
            raise KeyError(key)
        value, timestamp = result
        if timestamp < time.time() - self.ttl_seconds:
            self.__delitem__(key)
            raise KeyError(key)
        return pickle.loads(value)

    def __setitem__(self, key, value):
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
            (key, pickle.dumps(value), time.time()),
        )
        self._conn.commit()
```

Both classes implement `MutableMapping`. The `DummyCache` raises `KeyError` on every read and silently drops every write — the fetcher's `if key in self.cache` check fails, the fetcher does the network call, writes the result to cache (which goes nowhere), and moves on. No `if self.caching_enabled:` guards scattered through the fetcher code.

The `SQLiteCache` is deliberately minimal: one table, three columns (`key TEXT`, `value BLOB`, `timestamp REAL`). Values are pickled Python objects. TTL defaults to 24 hours and is checked lazily on read — expired entries are deleted on access, not by a background job.

**Cache key strategy** follows a `{type}:{identifier}` convention:
- `video_meta:{video_id}` — individual video metadata
- `channel_page:{normalized_url}` — the full initial page data (a 3-tuple of initial_data, ytcfg, and html)
- `continuation:{token}` — paginated continuation responses

This prefix convention enables targeted invalidation: `client.clear_cache(prefix="channel_page:")` wipes all channel data while preserving cached video metadata.

## Packaging: pyproject.toml and 13 Releases of Lessons Learned

```bash
sed -n '1,30p' pyproject.toml
```

```output
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "yt-meta"
version = "0.3.1"
description = "A lightweight, dependency-free library for fetching YouTube metadata."
readme = "README.md"
authors = [{ name = "Shane", email = "shane.isley@gmail.com" }]
license = { file = "LICENSE" }
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python",
    "Programming Language :: Python :: 3",
]
requires-python = ">=3.10"
dependencies = [
    "httpx",
    "beautifulsoup4",
    "dateparser",
    "pytz", # A dependency of dateparser
    "loguru",
    "diskcache>=5.6.3",
    "pytest-mock>=3.14.1",
    "rich>=14.0.0",
    "sqlitedict>=2.1.0",
    "youtube-comment-downloader>=0.1.76",
    "youtube-transcript-api>=1.1.0",
]
```

The build uses setuptools with a `pyproject.toml`-only configuration — no `setup.py`, no `setup.cfg`. Dev dependencies (`pytest`, `pytest-cov`, `ruff`) are cleanly separated via `[project.optional-dependencies]`.

Key dependency choices across 13 releases: **httpx** over requests (async-ready, even though only sync is used today). **dateparser** for YouTube's "2 weeks ago" relative timestamps. And notably, **diskcache** is still listed but was replaced by the hand-rolled `SQLiteCache` — simpler, and the `MutableMapping` interface made the swap invisible to all fetcher code.

The package targets Python 3.10+ — primarily for the `X | Y` union type syntax used throughout the codebase, which keeps type hints clean without importing `Union` from `typing`.

## Test Strategy: Mocks, Fixtures, and YouTube's Instability

```bash
cat tests/conftest.py
```

```output
# Key fixtures from tests/conftest.py (abbreviated)

def make_mock_html(player_response, initial_data, ytcfg=None):
    """Creates a minimal HTML structure for mocking video pages."""
    if ytcfg is None:
        ytcfg = {"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {}}
    # ... builds <script> tags embedding JSON for ytInitialPlayerResponse,
    #     ytInitialData, and ytcfg — mimicking real YouTube HTML

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# 10+ fixtures loading real captured HTML/JSON from YouTube:
# channel_page, youtube_channel_initial_data, bulwark_channel_initial_data, etc.

@pytest.fixture
def client() -> YtMeta:
    """Provides a cache-less YtMeta instance for unit testing."""
    return YtMeta(cache_path=None)

@pytest.fixture
def isolated_client(tmp_path) -> YtMeta:
    """YtMeta with a fresh, isolated cache in a temp directory per test."""
    cache_file = tmp_path / "test_cache.db"
    return YtMeta(cache_path=str(cache_file))
```

The test setup reveals a pragmatic strategy for testing against an unstable upstream API.

**Two client fixtures, two purposes.** `client()` creates a cache-less `YtMeta` (via `DummyCache`) for pure unit tests that mock all network calls. `isolated_client(tmp_path)` creates a real `SQLiteCache` in a pytest temp directory for cache-behavior tests — each test gets a fresh database that's cleaned up automatically.

**Captured fixtures over mocks where possible.** The `tests/fixtures/` directory contains real HTML pages and JSON responses captured from YouTube. Tests parse these fixtures through the same code paths as production, catching regressions in YouTube's response format changes. The `make_mock_html()` helper constructs minimal HTML with embedded JSON for cases where full page captures would be overkill.

**Integration tests are opt-in.** The `@pytest.mark.integration` marker separates tests that hit the real YouTube API. These validate that the parsing logic still works against YouTube's current format — critical for a scraping library — but they're excluded from CI by default to avoid flaky builds.

```bash
grep -rn 'def test_' tests/ | wc -l && echo 'test functions across:' && ls tests/test_*.py | wc -l && echo 'test files' && echo '---' && grep -rn '@pytest.mark.integration' tests/ | wc -l && echo 'integration tests'
```

```output
111
test functions across:
12
test files
---
22
integration tests
```

111 tests across 12 files, 22 tagged as integration. The ratio reflects the philosophy: validate parsing logic with frozen fixtures, spot-check the live API separately.

A representative unit test mocks the HTTP layer and verifies that the fetcher correctly handles a video that YouTube marks as unavailable:

```bash
sed -n '40,73p' tests/test_client.py
```

```output
def test_video_unavailable_raises_error(client, mocker):
    """
    Tests that a 404 response from session.get raises our custom error.
    """
    mocker.patch(
        "yt_meta.fetchers.VideoFetcher.get_video_metadata",
        side_effect=VideoUnavailableError("Video is private"),
    )
    with pytest.raises(VideoUnavailableError, match="Video is private"):
        client.get_video_metadata("dQw4w9WgXcQ")


def test_get_channel_metadata_unit(
    client, mocker, bulwark_channel_initial_data, bulwark_channel_ytcfg
):
    """
    Tests that channel metadata can be parsed correctly from a fixture file.
    """
    mocker.patch(
        "yt_meta.fetchers.ChannelFetcher._get_channel_page_data",
        return_value=(bulwark_channel_initial_data, bulwark_channel_ytcfg, None),
    )
    metadata = client.get_channel_metadata("https://any-url.com")
    assert metadata is not None
    assert metadata["title"] == "The Bulwark"


def test_get_video_metadata_live_stream_unit(client):
    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value.text = get_fixture("live_stream.html")
        mock_get.return_value.status_code = 200
        result = client.get_video_metadata("LIVE_STREAM_VIDEO_ID")
        assert result is None, "Should return None for unparseable live stream pages"

```

The mock patches at the fetcher boundary, not at the HTTP level — testing the Facade's delegation contract. The channel metadata test loads a real captured fixture and asserts on actual content, catching both parsing regressions and structural changes.

## Closing: Architecture as Documentation

The Facade pattern in yt-meta isn't academic — it solves a real packaging problem. When your library is consumed via `pip install`, the import surface *is* the product. A single `YtMeta` class with ten methods is something a caller can hold in their head. The five fetchers behind it can be restructured, split, or merged between releases without touching the public contract.

The key architectural decisions all reinforce this principle:
- **One entry point** (`YtMeta`) that wires together specialists the caller never sees
- **MutableMapping caches** that let fetchers stay cache-agnostic while the Facade controls the strategy
- **Generator-based pagination** that gives callers a simple `for` loop over potentially thousands of results
- **Fast/slow filter partitioning** that optimizes automatically without exposing the cost model
- **Captured fixtures** that test against real YouTube data without coupling the test suite to network availability

After 13 releases, the lesson is that good API design isn't about making things simple — it's about choosing which complexity to absorb so your callers don't have to.
