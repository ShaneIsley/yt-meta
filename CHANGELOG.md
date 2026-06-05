# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

- (Add new changes here)

## [0.5.0] - 2026-06-05

The "honor the values" release. Closes the on-disk cache RCE vector
(pickle → json), makes the cache thread-safe, replaces the unreliable
``__del__`` hooks with explicit ``close()`` / context-manager lifecycle,
and adds host validation at the network boundary. The default
``pytest`` invocation no longer hits live YouTube. Cache key handling
is canonicalized so a single video isn't fetched and stored multiple
times.

What ships here is the cache + lifecycle + security + CI half of the
v0.5.0 scope. The comment-subsystem unification (M1/L2) and
retry/backoff (H9) defer to v0.6.0 where they pair more naturally with
the rest of the comment-rehab work (H3/H4 continuation rewrite,
fixture-driven parser tests).

### Added
- ``YtMeta.close()``, ``__enter__``, ``__exit__`` for explicit resource
  cleanup. Closes the main ``httpx.Client``, the comment subsystem's
  ``httpx.Client``, and the SQLite cache connection. Idempotent. ``with
  YtMeta() as client:`` is now the recommended pattern. **H5**.
- ``CommentFetcher.close()`` and ``CommentAPIClient.close()`` as the
  explicit cleanup paths replacing the prior ``__del__`` hooks. Both
  classes are also context managers. **H5/M12**.
- ``DummyCache.close()`` no-op so all cache types share a uniform
  close interface. **H5**.
- ``SQLiteCache.close()`` factored out of ``__exit__`` (which now
  delegates to it). Both paths produce the same cleanup. **H5**.
- ``cache_ttl_seconds`` kwarg on ``YtMeta.__init__`` (default 86400 s,
  unchanged). Surfaces ``SQLiteCache``'s per-instance TTL so callers
  can pick the freshness window appropriate to their workload.
  Ignored when ``cache=`` is supplied (the injected cache has its own
  TTL semantics). **M10**.
- ``yt_meta.utils.validate_youtube_url(url)`` — small helper that
  raises ``ValueError`` if the URL hostname isn't in the YouTube
  allowlist (youtube.com / www.youtube.com / m.youtube.com /
  music.youtube.com / youtu.be). Called at the top of
  ``ChannelFetcher._get_channel_page_data`` and
  ``_get_channel_shorts_page_data``. **M13**.

### Changed
- ``SQLiteCache`` opens its connection with ``check_same_thread=False``
  and serializes all DB operations through a ``threading.Lock``. A
  single ``YtMeta`` is now safe to share across threads (e.g.
  ``ThreadPoolExecutor``, FastAPI request handlers, off-thread
  generator consumption). **H8**.
- ``SQLiteCache`` enables ``PRAGMA journal_mode=WAL`` and ``PRAGMA
  synchronous=NORMAL`` at construction. Concurrent reads no longer
  block on commits; durability is preserved across crashes. **H8**.
- ``VideoFetcher.get_video_metadata`` builds the cache key via
  ``utils.extract_video_id`` instead of an ad-hoc ``v=`` split.
  Different URL forms of the same video (``watch?v=ID``,
  ``watch?v=ID&t=42``, ``youtu.be/ID``, ``/shorts/ID``, bare ID) now
  share a single cache entry. **H6**.
- ``ChannelFetcher._get_channel_page_data`` and
  ``_get_channel_shorts_page_data`` cache ``(initial_data, ytcfg)``
  instead of ``(initial_data, ytcfg, html)``. The raw HTML was unused
  by all three call sites (each unpacked with ``_`` on the third
  slot) and bloated each entry by ~150-300 KB. **M11**.
- Default ``pytest`` invocation is offline. ``[tool.pytest.ini_options].addopts``
  now includes ``-m 'not integration'``. Run network-touching tests
  with ``pytest -m integration``. **H12**.
- ``utils.extract_video_id`` validates extracted IDs against
  ``[A-Za-z0-9_-]{11}``. The pass-through fallback that accepted any
  non-``http`` string ("test_id", "../etc/passwd", arbitrary garbage)
  is removed. **M13**.

### Security
- ``SQLiteCache`` swaps the on-disk format from ``pickle`` to ``json``.
  ``pickle.loads`` on a tampered cache file (multi-user host, shared
  volume, accidentally committed ``.db``, malicious tarball) executed
  arbitrary code in the next process that opened the file. ``json``
  closes that vector. Existing pre-0.5.0 cache files are detected by
  the leading pickle protocol marker (0x80) and raise a clean
  ``ValueError`` telling the user to delete the file — no silent
  rebuild, no auto-migration. The ``pickle`` module is removed from
  ``yt_meta/caching.py`` entirely. **H7**.
- Hostname allowlist on ``ChannelFetcher`` rejects URLs pointing
  outside YouTube before any network call. Forecloses an SSRF
  primitive for code paths that take channel URLs from user input.
  **M13**.
- Strict 11-character video-ID validation on ``utils.extract_video_id``
  prevents user-controlled strings from flowing into cache keys
  (``video_meta:{id}``), log lines, and URL construction. **M13**.

### Removed
- ``__del__`` hooks on ``CommentFetcher`` and ``CommentAPIClient`` —
  unreliable cleanup primitives that didn't run at interpreter
  shutdown, were skipped on reference cycles, and suppressed
  exceptions silently. Explicit ``close()`` / context-manager is now
  the only cleanup path. **M12**.

### Breaking changes
- **Cache file format**: existing ``.my_yt_meta_cache/cache.db`` (or
  any path passed to ``YtMeta(cache_path=...)``) written by yt-meta
  0.4.x or earlier raises ``ValueError`` on first read. Migration is
  a one-liner: delete the file and let yt-meta rebuild. The error
  message points there directly. **H7**.
- **Default ``pytest`` no longer runs integration tests**. CI configs
  that depended on the previous behavior must add ``-m integration``
  to their test command (or override the addopts entirely). **H12**.
- **``utils.extract_video_id`` rejects non-11-char inputs**. Code that
  passed test placeholders like "test_id" through the old
  pass-through fallback must use canonical video IDs. The fallback
  was a "for testing purposes" hack that also accepted arbitrary
  user-controlled strings. **M13**.
- **``ChannelFetcher`` rejects non-YouTube hostnames**. Calling
  ``client.get_channel_metadata("https://evil.example.com/...")`` now
  raises ``ValueError`` before any network call. **M13**.
- **``__del__`` is gone from comment classes**. Any code that relied
  on garbage-collection cleanup of ``CommentFetcher`` /
  ``CommentAPIClient`` resources must switch to ``close()`` or a
  ``with`` block. **M12**.

### Cache shape
- ``ChannelFetcher`` cache values changed from a 3-tuple
  ``(initial_data, ytcfg, html)`` to a 2-tuple
  ``(initial_data, ytcfg)``. Mostly internal — the three call sites
  in the library unpacked with ``_`` on the third slot — but if you
  reached into ``client.cache`` directly, the shape changed. **M11**.
- ``SQLiteCache`` round-trips tuples as lists (JSON has no tuple
  type). All current cache shapes are either tuple-unpacked
  (works on lists) or indexed (also works), so production code is
  unaffected. **H7**.

## [0.4.0] - 2026-06-05

The "make the docs match the code" release. Reconciles version drift (the
codebase had been shipping under 0.3.1 while a draft CHANGELOG entry
declared "2.0.0"; 0.4.0 is the honest landing point), wires the comment
filter DSL the README has been promising, fixes several documented APIs
that crashed on first use, and cleans up runtime dependency surface.

### Added (carried forward from the unreleased 2.0.0 draft — features that have been in 0.3.1)
- Video transcript fetching with language support via `TranscriptFetcher`
  and `client.get_video_transcript`.
- Native comment-fetching subsystem (`CommentFetcher`, `CommentAPIClient`,
  `CommentParser`) with hierarchical comments, reply continuation tokens,
  and enhanced metadata (`author_channel_id`, `author_avatar_url`,
  `reply_count`).
- Comment sorting (`sort_by='top'` and `sort_by='recent'`).
- `since_date` parameter on comment fetching that short-circuits
  pagination when combined with `sort_by='recent'`.

### Added (this release)
- `client.get_video_comments` and `get_video_comments_with_reply_tokens`
  now accept a `filters=` dict (text, author, like_count, reply_count,
  publish_date, is_reply, is_hearted_by_owner, is_by_owner, channel_id).
  Validated fail-fast via `validate_filters`. Operates on the in-memory
  comment list — does NOT reduce request count (only `since_date` does
  that). M19.
- `client.get_video_comments_with_reply_tokens` gains a `since_date`
  parameter for symmetry with `get_video_comments`.
- `YtMeta(cache=...)` accepts any `MutableMapping` (plain dict,
  `diskcache.Cache`, `sqlitedict`, etc.) in addition to the existing
  `cache_path=` parameter. Restores the documented injection point. H13.
- `yt-meta[persistent_cache]` extra now exists in `pyproject.toml`,
  matching the README. M16.

### Changed
- **Default `sort_by` flipped from `'top'` to `'recent'`** on
  `client.get_video_comments`, `get_video_comments_with_reply_tokens`,
  and `CommentFetcher.get_comments`. Aligns code with the README's
  documented intent and with the project's metadata-retrieval identity
  (raw chronological stream > YouTube's editorial ranking). Also makes
  `since_date` short-circuit by default. H14 (default-sort half).
- `VideoFetcher.get_video_id` now delegates to `utils.extract_video_id`
  and emits a `DeprecationWarning`. The three Facade call sites switched
  to `extract_video_id` directly. Adds `youtu.be/` URL support to all
  comment-fetching methods. M17.
- `parse_relative_date_string` now delegates unrecognized strings to
  `dateparser.parse` (so `'2023-01-01'` works as documented) and raises
  `ValueError` when parsing fails. Non-str inputs (e.g. `None`) still
  return today as a defensive fallback. H2.
- `client.get_video_comments` and `get_video_comments_with_reply_tokens`
  widen `limit` from `int` to `int | None`. Passing `None` or `-1` for
  unbounded fetching now requires `since_date` to be set; a `ValueError`
  is raised otherwise. Prevents runaway pagination on popular videos.
  M19 safety guard.
- README rewritten: API reference for `get_video_comments` matches the
  real signature (no more fabricated `SORT_BY_RECENT`/`SORT_BY_POPULAR`
  constants); comment example uses the real `like_count` field; Library
  Architecture section no longer claims `VideoFetcher` "fetches comments"
  or that `YtMeta` "inherits from `youtube-comment-downloader`". H14
  (doc half), H15, M18.

### Fixed
- `PlaylistFetcher.get_playlist_videos` no longer crashes with
  `AttributeError` when `start_date` or `end_date` is passed. The filter
  was being built as a tuple (`(">=", date)`) instead of the dict shape
  (`{"gte": date}`) used by `ChannelFetcher`. H1.

### Removed (runtime dependencies)
- `loguru`, `beautifulsoup4`, `sqlitedict`, `youtube-comment-downloader`,
  `rich`, `pytz` removed from `[project.dependencies]` — none were
  imported in `yt_meta/`. `pytest-mock` moved from runtime deps to
  `[project.optional-dependencies].dev` and `[dependency-groups].dev`.
  `diskcache` moved from runtime deps to the new
  `[project.optional-dependencies].persistent_cache`. H10 (partial).

### Packaging
- `[tool.setuptools.packages.find]` now sets `include = ["yt_meta*"]` so
  the `tests/` directory is no longer shipped in the wheel. H11.

### Breaking changes summary
- `parse_relative_date_string('garbage')` raises `ValueError` instead of
  silently returning today.
- Default `sort_by` for all three comment methods is now `'recent'`.
  Callers depending on `'top'` ordering must pass `sort_by='top'`
  explicitly.
- `VideoFetcher.get_video_id` emits `DeprecationWarning`; will be removed
  in 0.6.0.
- Unbounded comment fetching (`limit=None` or `limit=-1`) requires
  `since_date`.
- Runtime deps shrunk; environments that consumed `loguru`/`beautifulsoup4`/
  `sqlitedict`/`youtube-comment-downloader`/`rich`/`pytz` transitively
  must install them explicitly. `diskcache` is now installed via the
  `yt-meta[persistent_cache]` extra.

---

For earlier changes, see project history or previous release notes.
