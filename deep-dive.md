# yt-meta: Facade Pattern as API Design Philosophy

*2026-03-18T22:07:01Z by Showboat 0.6.1*
<!-- showboat-id: f4c97375-da20-482a-8034-7a39713610ef -->

## The Interface IS the Product

yt-meta is a Python library for fetching YouTube metadata — video, channel, playlist, comments, and transcripts — without the YouTube Data API. It scrapes YouTube's internal JSON payloads instead, and it has shipped 13 releases on PyPI. At v0.4.0, the library is used by developers who need YouTube data without OAuth, quotas, or API keys.

That context matters for every architectural decision in the codebase. This is a *published* package. The public interface isn't just documentation — it's a contract. Break it and you break downstream code you can't see. Every decision in the design reflects that constraint.

The consumer-facing surface is deliberately minimal. Here's everything a user imports:

```bash
grep -n '__all__' yt_meta/__init__.py -A 10
```

```output
12:__all__ = [
13-    "YtMeta",
14-    "MetadataParsingError",
15-    "VideoUnavailableError",
16-    "parse_relative_date_string",
17-    "CommentFetcher",
18-    "BestCommentFetcher",  # Backward compatibility
19-    "CommentAPIClient",
20-    "CommentParser",
21-]
```

One class, two exceptions, one utility function. The rest of the exports are backward-compatibility aliases. This compression of surface area is a deliberate choice — users only need `YtMeta`, and that's the entry point to everything.

---

## The Facade: One Client, Five Fetchers

The Facade pattern here is explicit — the class docstring says so.

```bash
sed -n '19,49p' yt_meta/client.py
```

```output
class YtMeta:
    """
    A client for fetching metadata for YouTube videos, channels, playlists, and comments.
    This class acts as a Facade, delegating calls to specialized fetcher classes.
    """

    def __init__(self, cache_path: str | None = None):
        """
        Initializes the yt-meta client.

        Args:
            cache_path: If provided, the path to a SQLite file for persistent,
                        on-disk caching. If None (the default), caching is disabled.
        """
        self.session = Client(headers={"Accept-Language": "en-US,en;q=0.5"})
        if cache_path:
            self.cache = SQLiteCache(path=cache_path)
            logger.info(f"Using SQLite cache at: {cache_path}")
        else:
            self.cache = DummyCache()
            logger.info("Caching is disabled.")

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

The constructor tells the whole structural story. One shared `httpx.Client` session. One cache object. Five fetchers, all wired together. The `VideoFetcher` instance is passed into `ChannelFetcher` and `PlaylistFetcher` — because fetching full video metadata for a list of channel videos is the `VideoFetcher`'s job, not the channel's.

This is the key architectural question: why five fetchers instead of one big class?

The alternative would be a single 600-line client with mixed concerns — pagination logic for channels sitting next to comment parsing, transcript fetching next to playlist continuation tokens. The Facade keeps the public API small while the fetchers can be developed, tested, and reasoned about independently.

Each public method on `YtMeta` is a thin delegation:

```bash
sed -n '84,95p' yt_meta/client.py
```

```output
    def get_video_metadata(self, youtube_url: str) -> dict:
        """
        Fetches and parses comprehensive metadata for a given YouTube video.

        Args:
            youtube_url: The full URL of the YouTube video.

        Returns:
            A dictionary containing detailed video metadata.
        """
        return self._video_fetcher.get_video_metadata(youtube_url)

```

Every public method follows this pattern. The Facade is pure forwarding — no business logic lives in `client.py` except argument validation and date resolution. Users never interact with fetchers directly.

---

## Deep Dive: ChannelFetcher — Pagination, Error Recovery, and Caching

`ChannelFetcher` is the most complex fetcher. It handles two distinct content types (videos and shorts), YouTube's multi-page continuation API, and intelligent early-stopping based on date filters.

### Pagination

YouTube renders channel pages with a fixed first page of ~30 videos, then provides continuation tokens for subsequent pages. The fetcher discovers the token from the initial HTML, then hits YouTube's internal API:

```bash
sed -n '73,87p' yt_meta/fetchers.py
```

```output
    def _get_continuation_data(self, token: str, ytcfg: dict):
        cache_key = f"continuation:{token}"
        if cache_key in self.cache:
            self.logger.info(f"Cache hit for continuation token: {token[:10]}...")
            return self.cache[cache_key]
        data = {"context": ytcfg["INNERTUBE_CONTEXT"], "continuation": token}
        response = self.session.post(
            f"https://www.youtube.com/youtubei/v1/browse?key={ytcfg['INNERTUBE_API_KEY']}",
            json=data,
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
        self.cache[cache_key] = result
        return result
```

This is the internal `youtubei/v1/browse` endpoint — the same JSON API YouTube's own frontend uses. The `ytcfg` dict extracted from the page HTML contains the API key and the context object required for the request.

Notice the cache check-before-fetch, cache-after-fetch pattern. Every network call is wrapped this way. Continuation responses are cached by their token, so paginating through the same channel twice doesn't cost extra requests.

### Pagination Loop with Early Stopping

The pagination loop has one important optimization: it stops fetching pages as soon as it finds a video older than the requested start date.

```bash
sed -n '304,332p' yt_meta/fetchers.py
```

```output
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

```

YouTube channels display videos newest-first. When a `start_date` is given, once the loop encounters a video older than that date, it sets `stop_pagination = True`. The current page still finishes (because `yield video` runs before the check), then the outer loop breaks without making another HTTP request. This is O(pages_needed) rather than O(total_pages).

### Error Recovery

The fetcher distinguishes between two error classes: `VideoUnavailableError` (network/HTTP failures) and `MetadataParsingError` (structural failures). Network errors at the initial page load propagate up. Network errors during metadata enrichment are caught per-video, logged, and skipped — a failed video doesn't abort the whole channel crawl.

```bash
sed -n '56,63p' yt_meta/fetchers.py
```

```output
                            continue
                except (VideoUnavailableError, MetadataParsingError) as e:
                    self.logger.error(
                        "Error fetching metadata for video_id %s: %s",
                        video["video_id"],
                        e,
                    )
                    continue
```

---

## The Caching Layer

Caching is optional but first-class. The design uses the `MutableMapping` protocol as the cache interface, which means any dict-like object works — `DummyCache` (a no-op), `SQLiteCache` (the default persistent option), or any custom implementation.

### The Null Object Pattern

`DummyCache` is a Null Object — it implements the interface but does nothing:

```bash
sed -n '11,28p' yt_meta/caching.py
```

```output
class DummyCache(MutableMapping):
    """A dummy cache that stores nothing. Used when caching is disabled."""

    def __getitem__(self, key):
        raise KeyError(key)

    def __setitem__(self, key, value):
        pass

    def __delitem__(self, key):
        pass

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0

```

The Null Object means all fetcher code can call `self.cache[key]` without branching on whether caching is enabled. The cache is always present; its behavior changes based on which implementation was injected at construction time.

### Cache Key Strategy

Keys are namespaced by resource type with a colon prefix:

```bash
grep -n 'cache_key' yt_meta/fetchers.py
```

```output
74:        cache_key = f"continuation:{token}"
75:        if cache_key in self.cache:
77:            return self.cache[cache_key]
86:        self.cache[cache_key] = result
109:        cache_key = f"video_meta:{video_id}"
110:        if cache_key in self.cache:
112:            return self.cache[cache_key]
137:        self.cache[cache_key] = result
161:    def _get_channel_page_cache_key(self, channel_url: str) -> str:
167:    def _get_channel_shorts_page_cache_key(self, channel_url: str) -> str:
176:        key = self._get_channel_page_cache_key(channel_url)
208:        key = self._get_channel_shorts_page_cache_key(channel_url)
```

The prefixes — `video_meta:`, `continuation:`, `channel_page:`, `channel_shorts_page:` — serve a practical purpose. The public `clear_cache(prefix=)` method uses string prefix matching to invalidate by resource type. Want to bust only the cached video pages without clearing channel data? `client.clear_cache(prefix='video_meta:')`.

### SQLiteCache: TTL and Serialization

```bash
sed -n '30,68p' yt_meta/caching.py
```

```output
class SQLiteCache(MutableMapping):
    """
    A cache that uses SQLite as a backend.
    """

    def __init__(self, path=".my_yt_meta_cache/cache.db", ttl_seconds=86400):
        self.path = path
        self.ttl_seconds = ttl_seconds
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value BLOB, timestamp REAL)"
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._conn.close()

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

Several decisions worth noting here:

**TTL-on-read invalidation.** Expired entries are evicted on access — no background sweep thread. For a scraping library used in batch jobs this is the right tradeoff: no overhead, stale entries persist until accessed.

**Pickle serialization.** Cache values are arbitrary Python objects. Pickle handles them without a schema — Python-only and version-sensitive, but fine for a single-language library.

**SQLite over diskcache.** Early versions used `diskcache`. The switch to hand-rolled SQLite gave full control over TTL and schema. The table is three columns: key, value blob, timestamp.

---

## Packaging: pyproject.toml and 13 Releases

```bash
cat pyproject.toml
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

[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "pytest-mock", "ruff", "tqdm"]

[project.urls]
Homepage = "https://github.com/shaneisley/yt-meta"

[tool.setuptools.packages.find]
where = ["."]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
markers = [
    "integration: marks tests as integration tests (makes network requests)",
]
filterwarnings = [
    "ignore:Parsing dates involving a day of month without a year specified is ambiguous:DeprecationWarning",
]

[dependency-groups]
dev = [
    "pytest>=8.4.1",
    "tqdm>=4.67.1",
]

[tool.ruff]
# Exclude a variety of commonly ignored directories.
# ... existing code ...

[tool.ruff.lint]
# By default, ruff will lint all files in the current directory and its subdirectories
# except for those that are excluded by .gitignore, .ignore, .ruff_ignore, or global-exclude.
# You can override this behavior by specifying the `select` option.
select = [
    "E",  # pycodestyle errors
    "W",  # pycodestyle warnings
    "F",  # pyflakes
    "I",  # isort
    "B",  # flake8-bugbear
    "C4", # flake8-comprehensions
    "UP", # pyupgrade
]
ignore = [
    "E501", # Line too long, handled by black
]

[tool.uv.sources]
yt-meta = { path = ".", editable = true }
```

There's a tension in the dependency list. The description says "lightweight, dependency-free" but 10 packages are listed, including `diskcache`, `sqlitedict`, and `pytest-mock`. Some are legacies from earlier phases that haven't been cleaned up — `diskcache` is still declared even though the cache layer was rewritten to use plain `sqlite3`. `pytest-mock` is a test dependency that leaked into runtime deps.

This is API evolution in the open: early decisions compound. Cleaning them up requires a semver bump and a deprecation cycle. `BestCommentFetcher` is still exported with a "Backward compatibility" comment — a renamed class that can't be removed without breaking users.

**uv as build toolchain.** `[tool.uv.sources]` enables editable installs with a lockfile (`uv.lock`), giving reproducible environments without manual environment management.

---

## The Fast/Slow Filter Architecture

```bash
sed -n '22,38p' yt_meta/filtering.py
```

```output
FAST_VIDEO_FILTERS = {
    "view_count",
    "duration_seconds",
    "publish_date",
    "title",
    "description_snippet",
}
FAST_SHORTS_FILTERS = {"view_count", "title"}

# These keys require fetching full metadata for each video, making them slower.
SLOW_FILTER_KEYS = {
    "like_count",
    "category",
    "keywords",
    "full_description",
}

```

This is an important API design decision. YouTube's channel page gives you a subset of video metadata for free: view count, title, duration, publish date, and a description snippet. Filters on those fields cost nothing extra.

Filters on `like_count`, `category`, or `keywords` require a separate GET request per video to the watch page. The library calls these "slow filters" and automatically sets `fetch_full_metadata=True` when they're requested, logging a warning if the user didn't explicitly opt in.

This makes a performance cost explicit in the API surface. The caller can look at the filter key names and know which operations are O(1) page loads versus O(n) per-video requests — without reading implementation code.

---

## Test Strategy: Mocks Against YouTube's Instability

```bash
ls tests/fixtures/ | head -20
```

```output
B68agR-OeJM.html
ai_makerspace_channel_renderers_last_sample.json
aimakerspace_channel_initial_data.json
aimakerspace_channel_video_renderers.json
aimakerspace_channel_ytcfg.json
bulwark_channel_initial_data.json
bulwark_channel_video_renderers.json
bulwark_channel_ytcfg.json
channel_page.html
comment_continuation_response.json
comment_reply_response.json
continuation_fixture.json
debug_continuation_response.json
live_stream.html
mr_beast_shorts_page.html
playlist_118_videos.html
playlist_145_videos.html
playlist_3_videos.html
playlist_continuation_response.json
playlist_page.html
```

```bash
ls tests/fixtures/ | wc -l && ls tests/test_*.py | wc -l
```

```output
23
12
```

YouTube changes its internal JSON structures without notice. The test strategy is built around this: 23 fixture files capture real HTML pages and JSON API responses from multiple channels (Bulwark, AI Makerspace, MrBeast) and page types (channel, playlist, comments, shorts). Tests run against snapshots, not live HTTP.

12 test files cover the full stack:

```bash
ls tests/test_*.py
```

```output
tests/test_caching.py
tests/test_channel_fetcher.py
tests/test_client.py
tests/test_comment_fetcher.py
tests/test_date_utils.py
tests/test_filtering.py
tests/test_parsing.py
tests/test_playlist.py
tests/test_playlist_fetcher.py
tests/test_transcript_fetcher.py
tests/test_validation.py
tests/test_video_fetcher.py
```

```bash
grep -n '@pytest.mark.integration' tests/test_client.py | head -8
```

```output
225:@pytest.mark.integration
234:@pytest.mark.integration
244:@pytest.mark.integration
254:@pytest.mark.integration
266:@pytest.mark.integration
276:@pytest.mark.integration
```

Tests are organized in two tiers using pytest markers:

- **Unit tests** use `mocker.patch` (pytest-mock) and fixture files. They run offline, in CI, on every push.
- **Integration tests** marked with `@pytest.mark.integration` make real HTTP requests against live YouTube URLs. They're opt-in, not part of the default CI run.

Multiple channels are represented so tests don't depend on a single channel's structure. When YouTube changes its schema: update the fixture, fix the parser, tests pass.

```bash
sed -n '40,70p' tests/test_client.py
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
```

Mocks are at the HTTP boundary — `_get_channel_page_data` returns fixture data, and real parsing runs against it. You're not testing that HTTP works; you're testing that parsing works given known inputs. When YouTube changes its schema, fixture-loaded JSON fails to parse, surfacing regressions before users hit them.

---

## Summary: What 13 Releases Teaches About API Design

The Facade pattern in yt-meta serves a specific goal: make the library feel simple to use while keeping the internals evolvable. The public surface is stable — `YtMeta`, its methods, and their signatures. The internals (fetchers, parsers, cache backends) have been refactored across releases without breaking callers.

The decisions that aged best:
- **MutableMapping as the cache interface** — swap backends without touching fetchers
- **Generators for collection endpoints** — callers can `break` early without wasting HTTP requests
- **Typed exceptions** (`VideoUnavailableError`, `MetadataParsingError`) — callers can handle network failures separately from structural failures
- **Fast/slow filter split** — makes performance cost visible in the API rather than hidden in implementation

The decisions that created debt:
- **`diskcache` in the dependency list after moving to plain sqlite3** — dead weight that inflates the install footprint
- **`pytest-mock` in runtime dependencies** — a test tool that shouldn't be in `dependencies`
- **The `BestCommentFetcher` alias** — a renamed class that's now permanently in the public API

The overall arc is: ship early, use the feedback from real use to drive the design, and accept that a public API is harder to clean up than a private one.
