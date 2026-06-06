# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

- (Add new changes here)

## [0.7.0] - 2026-06-06

Video-status and edge-case release: surfaces availability/upcoming/live
status on single videos, adds the Live (`/streams`) tab, flags
members-only and upcoming items in listings, fixes reply-token
extraction against YouTube's current shape, and replaces the brittle
value-asserting integration tests with a structural live contract
suite.

### Changed
- `is_live` on `get_video_metadata` now means *currently streaming*
  (from `liveBroadcastDetails.isLiveNow`) rather than
  `videoDetails.isLiveContent` — the old value was also `True` for
  upcoming videos and ended live VODs. The not-yet-started case is now
  covered explicitly by `is_upcoming` + `scheduled_start_time`. This is
  the one behavioral change in this release; all other additions are
  additive.

### Tests
- Added a rarely-run live **contract test** (`pytest -m contract`) that
  asserts the structural shape YouTube returns (types, key presence,
  permanent identifiers) rather than volatile values — so a real
  structure change fails loudly instead of looking like a network
  flake. Removed the 22 brittle value-asserting `integration` tests it
  supersedes; live coverage now lives in one place.

### Added
- **`get_channel_streams()` — the Live (`/streams`) tab.** Live,
  upcoming/scheduled, and past live streams live on a channel's Live
  tab, which is *separate* from Videos — `get_channel_videos` never saw
  them. The new method fetches that tab (same item shape as
  `get_channel_videos`). Upcoming streams carry `is_upcoming=True` and
  `scheduled_text` (the listing's "Scheduled for …"); pass
  `fetch_full_metadata=True` for the precise `scheduled_start_time` and
  `status` per stream. Live-verified against @AppleDeveloper/streams.
- **`is_upcoming` / `scheduled_text` on channel-video listings.**
  `parse_lockup_view_model` now flags scheduled items (a "Scheduled
  for …" / "Premieres …" metadata part) as `is_upcoming=True` with the
  raw `scheduled_text`.
- **Upcoming / live status on `get_video_metadata`.** Scheduled
  premieres and not-yet-started live events now report `status="upcoming"`
  with `is_upcoming=True` and a `scheduled_start_time` (ISO-8601, from
  the watch page's `liveBroadcastDetails`). Live-verified against a real
  scheduled premiere. The `is_live` field now means *currently
  streaming* (`liveBroadcastDetails.isLiveNow`) — it previously used
  `videoDetails.isLiveContent`, which is also `True` for upcoming videos
  and ended live VODs, so it was misleading.
- **`is_members_only` on channel-video listings.** `get_channel_videos`
  now flags members-only videos (detected from the `BADGE_MEMBERS_ONLY`
  lockup badge) with an explicit `is_members_only` boolean, instead of
  callers having to infer it from a `None` view count. Live-verified
  against a channel with members-only uploads. (Live/upcoming listing
  badges remain a follow-up pending fixtures.)
- **Video availability status on `get_video_metadata`.** Every result
  now carries `status` (`"ok"` / `"unavailable"`), `status_reason`
  (YouTube's text when unavailable), and ISO-8601 UTC
  `status_checked_at` / `status_changed_at` timestamps. Previously a
  deleted/unavailable video returned a junk dict (`title=None`,
  `view_count=0`) with no signal; now it's explicit. When a
  previously-`ok` video becomes `unavailable`, the result PRESERVES the
  last-known-good content fields and stamps the change time — so prior
  data isn't lost. New `force_refresh=True` parameter re-checks a cached
  video to pick up status changes. Derived from `playabilityStatus` in
  the watch-page player response; finer-grained statuses (private,
  members-only, age-restricted, upcoming) are reserved for a follow-up
  once live fixtures are captured.

### Fixed
- **Reply continuation tokens** are extracted again. YouTube moved the
  token from `commentRepliesRenderer.contents[]` to `.subThreads[]`;
  `get_video_comments_with_reply_tokens` / `get_comment_replies` had
  silently stopped surfacing tokens (comments with hundreds of replies
  returned none). Both shapes are now handled.
- `extract_video_id` now handles `/live/<id>` URLs (the form YouTube
  uses for live streams and scheduled premieres, often with a `?si=`
  share param). Previously such links raised `ValueError`.
- `get_video_metadata` now builds a canonical watch URL from the
  resolved video id, so a bare 11-char id (or `youtu.be/` link) works
  — previously it fetched the raw input as a URL and raised for bare
  ids.
- Refined the None-return contract: `get_video_metadata` returns `None`
  only when the page yields no player response at all. Pages with a
  player response but missing `ytInitialData` (optional enrichment) now
  parse to a status-bearing dict instead of `None`.

## [0.6.2] - 2026-06-05

### Added
- **``YtMeta(accept_cookies=True)`` — opt-in EU cookie-consent bypass.**
  In some regions (e.g. the EU) YouTube responds to channel/video
  requests with a ``302`` redirect to ``consent.youtube.com`` before
  serving any content, which surfaced as an ``HTTPStatusError`` (issue
  #1, reported by @iAmInActions). Passing ``accept_cookies=True`` sets
  YouTube's ``SOCS`` consent cookie on the shared session so content is
  served directly. Default is ``False`` — no cookie is set and behavior
  is unchanged — because setting a consent cookie on the user's behalf
  should be a conscious, explicit choice, not a silent side effect.
  Because the comment overhaul (M1/L2 in 0.6.0) unified all fetchers
  onto one session, the single opt-in covers video, channel, playlist,
  and comment fetches alike. Supersedes the narrower per-fetcher
  approach proposed in PR #2.

  Note: this could not be verified against the live consent wall from
  the development environment (not region-gated); the cookie is
  confirmed set and harmless on the normal path, but EU confirmation
  relies on affected users.

## [0.6.1] - 2026-06-05

A critical fast-follow fix for ``get_channel_videos``, which was
returning zero videos for every channel.

### Fixed
- **``get_channel_videos`` parses YouTube's new ``lockupViewModel``
  channel-video format.** YouTube migrated the channel "Videos" tab
  from ``videoRenderer`` to ``lockupViewModel``; the extraction loop
  only recognized the old shape, so every item was skipped — the
  method returned nothing and then paginated fruitlessly (up to ~100
  wasted continuation requests per channel). This was the real cause
  of the long-standing "flaky" channel integration failures
  (``assert 0 == N``), not rate-limiting. A 10-channel live harness
  confirmed 0/10 → 10/10 after the fix, with a single page fetch and
  no wasted pagination.

  New ``parsing.parse_lockup_view_model`` /
  ``parsing.extract_videos_from_lockup_renderers``; the channel-videos
  generator now branches on the renderer shape (``lockupViewModel``
  current, ``videoRenderer`` fallback). Handles the collab-byline and
  members-only (no view count) edge cases found by directly probing
  live pages. Playlists were probed too and are unaffected (still
  ``playlistVideoRenderer``).

  Covered by 5 offline regression tests against a captured real
  channel page (``tests/fixtures/channel_videos_lockup_renderers.json``),
  turning the previously-untestable path into provable coverage.

## [0.6.0] - 2026-06-05

The "pay down the debt" release — the terminal release from the
ultra-review roadmap. Rehabilitates the comment subsystem (unified
under the Facade's shared session+cache, continuation-token extraction
rewritten, pagination fixed, real-fixture test coverage), reduces
architectural strain (date-filter and video-pipeline logic extracted
into testable helpers), clears the deprecations from v0.4.0, hardens
parsing against real-world payload variation, and adds retry/backoff.
After this the project sits at a stable pre-1.0 line.

### Added
- In-house HTTP retry/backoff (``yt_meta/_retry.py``). Retries on
  429/5xx and connection errors with exponential backoff + full
  jitter, honoring ``Retry-After``. Wired into the channel/playlist
  continuation loop and the comment API loop;
  ``CommentAPIClient(retries=...)`` is now actually used. **H9**.
- ``YtMetaError`` base exception exported from the package top-level —
  ``except YtMetaError:`` now works as the README documents. **M8**.
- Video-targeting methods accept ``youtube_url`` and ``video_id``
  interchangeably (keyword aliases). ``get_video_transcript`` now
  routes its input through ``extract_video_id`` so URLs and youtu.be
  links work (previously a URL silently failed). **M9**.
- ``after`` / ``before`` are now valid operators on ``publish_date``
  filters (readable aliases for ``gt`` / ``lt``), accepted by
  ``validate_filters``. **M22**.
- Real-fixture test coverage for ``CommentParser`` using the 2.4 MB of
  previously-unused captured payloads in ``tests/fixtures/``. **H17/L6**.

### Changed
- Comment subsystem unified under the Facade's resources:
  ``CommentFetcher`` / ``CommentAPIClient`` accept an injected
  ``session`` and ``cache``, and ``YtMeta`` passes its own in. The
  library now uses ONE ``httpx.Client`` and ONE cache end-to-end;
  watch-page parses are cached under a shared ``video_initial:{id}``
  key. **M1/L2**.
- ``extract_continuation_token`` rewritten to walk the documented
  ``onResponseReceivedEndpoints`` path explicitly instead of a
  free-form DFS that could pick up a nested reply-continuation token
  and silently truncate the comment stream. **H3**.
- Comment pagination tolerates transient all-duplicate pages (a
  consecutive-empty-page counter) instead of breaking on the first
  one. **H4**.
- ``parse_video_metadata`` returns ``publish_date`` as a ``datetime``
  (was a raw ISO string), matching ``parse_video_renderer`` and the
  rest of the library. **M4** — see Breaking changes.
- Date-filter construction extracted into a single
  ``filtering.build_date_filter`` helper shared by the channel and
  playlist fetchers (eliminates the divergence that allowed the
  v0.4.0 H1 bug). **L1/M5**.
- The filter-pipeline epilogue (partition → fetch-decision → per-video
  loop) extracted into module-level ``_run_filtered_pipeline`` /
  ``_process_videos``, unit-testable without a fetcher instance.
  ``_BaseFetcher`` slimmed to its genuinely-shared members. **L5**.
- ``get_video_metadata`` annotation corrected to ``-> dict | None`` and
  docstring/README aligned: parse failures return ``None``, fetch
  failures raise ``VideoUnavailableError``. **M7**.
- ``apply_filters`` emits a DEBUG log when a video is dropped for a
  missing filter field (behavior unchanged; now discoverable). **M6**.
- The comment-fetch error handler narrowed from ``except Exception`` to
  httpx errors, so programmer bugs (KeyError etc.) surface unwrapped
  instead of being mislabeled "video unavailable". **M23**.

### Fixed
- ``parse_video_renderer`` no longer crashes on a badge entry with an
  explicit ``metadataBadgeRenderer: None``. **M2**.
- ``_get_raw_shorts_generator`` no longer raises ``IndexError`` when
  the shorts parser returns an empty result for an unexpected
  renderer shape (in-feed ads, A/B-test wrappers). **M3**.

### Removed
- ``CommentAPIClient``, ``CommentParser``, and the ``BestCommentFetcher``
  alias are no longer re-exported from the package top-level. Import
  them from their submodules if you need the internals. **M14**.
- ``VideoFetcher.get_video_id`` (deprecated in v0.4.0) is removed. Use
  ``yt_meta.utils.extract_video_id``. **M17**.

### Breaking changes
- **``publish_date`` is now a ``datetime``** in ``get_video_metadata``
  results (was a raw ISO string). Code doing string operations on the
  field must switch to datetime methods. **M4**.
- **Top-level imports of ``CommentAPIClient`` / ``CommentParser`` /
  ``BestCommentFetcher`` raise ``ImportError``** — use the submodule
  path. **M14**.
- **``VideoFetcher.get_video_id`` removed.** **M17**.
- **``CommentFetcher.__init__`` signature changed** (gained
  ``session`` / ``cache`` parameters). Standard usage via ``YtMeta``
  is unaffected; only direct constructors that relied on the exact
  prior signature need review. **M1/L2**.
- **``extract_video_id`` (and therefore the transcript path) rejects
  non-11-char inputs** more strictly via M9's routing — placeholder
  strings that previously slipped through now raise ``ValueError``.

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
