# yt-meta — Ultra Code Review

**Date:** 2026-06-02
**Scope:** Whole repo at `main` (no diff to review against). 5 parallel reviewers (correctness, architecture, caching/concurrency, deps/security, tests/docs) → synthesis. 40 findings kept (17 high, 23 medium), 16 dropped as low-signal.

## Executive summary

The codebase has a clean shape but ships several real correctness bugs, a packaging story that contradicts itself, and weakest-link test coverage on its newest subsystems (transcripts, overhauled comments).

**Top three priorities:**
1. Fix the `PlaylistFetcher` tuple-shaped filter bug (`fetchers.py:596`) and the `parse_relative_date_string` silent-today fallback (`date_utils.py:57`) — both make *documented* APIs crash or silently return wrong data.
2. Clean packaging — drop ~6 unused/test-only runtime deps (`loguru`, `beautifulsoup4`, `sqlitedict`, `youtube-comment-downloader`, `pytest-mock`, `rich`), exclude `tests/` from the wheel, and reconcile version drift (`__init__.py` says 0.3.1; CHANGELOG announces 2.0.0).
3. Replace `pickle` in `SQLiteCache` with `json` to close the RCE vector, and add `YtMeta.close()`/`__enter__`/`__exit__` so `httpx.Client` and the SQLite connection stop leaking.

Biggest latent risk: the comment subsystem is architecturally siloed (own `httpx.Client`, ignores shared cache, fragile DFS continuation-token extractor that can silently truncate results) and the README documents APIs that don't exist (`cache=` kwarg, `SORT_BY_RECENT`, `filters=` on `get_video_comments`, `comment['likes']`). What's genuinely good: parsing and filtering are well-tested with real fixtures; the exception hierarchy carries structured context; the Facade is the right abstraction; the channel-side date filter pipeline is correctly designed — it just needs to be reused everywhere instead of reinvented.

---

## Critical / High severity

### Correctness

**H1 — Playlist `start_date`/`end_date` builds a tuple filter that crashes downstream.** `yt_meta/fetchers.py:595-603`
`filters["publish_date"] = (">=", start_date)`, `("<=", end_date)`, or `("between", (a, b))`. But `apply_filters` (`filtering.py:218`) iterates `.items()` on the value — tuples have no `.items()`. The operators `>=`, `<=`, `between` aren't in the schema or `_check_date_condition` either. `ChannelFetcher` uses the *correct* dict shape (`fetchers.py:442`). Any caller passing `start_date=`/`end_date=` to `get_playlist_videos` raises `AttributeError` on first yield. **Fix:** reuse `ChannelFetcher`'s dict-merge idiom; extract a single `_build_date_filter(start, end)` helper.

**H2 — `parse_relative_date_string` silently returns *today* for unrecognized formats, including ISO dates.** `yt_meta/date_utils.py:57`
Final branch is `return datetime.today().date()`. Reached from `YtMeta._resolve_date` (`client.py:334`) and `ChannelFetcher.get_channel_videos` when `start_date`/`end_date` is a string. A user passing `start_date='2023-01-01'` gets *today* — channel pagination short-circuits immediately, date filters silently mismatch, no error raised. The `_resolve_date` docstring promises YYYY-MM-DD support. **Fix:** delegate non-shorthand strings to `dateparser.parse`; raise `ValueError` on failure.

**H3 — Comment continuation-token extraction can return a *reply* token, silently truncating results.** `yt_meta/comment_api_client.py:295`
`extract_continuation_token` does DFS over the whole API response returning the first `continuationCommand.token` for which `_is_comment_token` returns True — and `_is_comment_token` (line 215) accepts any token containing `'replies'`. Reply continuation tokens are embedded inside per-thread renderers, which DFS reaches before the bottom-of-page next-comments token. When that happens, the next call returns replies/duplicates, every id is in `seen_ids`, `found_comments` stays False, and `comment_fetcher.py:140-141` breaks the loop. **Fix:** walk the documented path explicitly (`onResponseReceivedEndpoints[*].reloadContinuationItemsCommand.continuationItems[-1]…continuationCommand.token`, plus the `appendContinuationItemsAction` variant) or exclude tokens nested under `commentRepliesRenderer`. Use the existing 600 KB fixture for a regression test.

**H4 — Comment fetcher breaks pagination on the first all-duplicate page.** `yt_meta/comment_fetcher.py:140`
`if not found_comments: break`. For `sort_by='top'`, pages can legitimately repeat across requests due to ranking quirks — first such repeat truncates results without consulting the continuation token for the *next* page. Compounds H3: if the wrong token was extracted, this break is what hides the truncation. **Fix:** consecutive-empty-page counter (break after 2–3) or check that the continuation token has actually advanced.

### Architecture / API

**H5 — `YtMeta` has no `close()` / `__enter__` / `__exit__`; `httpx.Client` and SQLite connection leak.** `yt_meta/client.py:33`
Constructor creates `self.session = Client(...)` and `self.cache = SQLiteCache(path=...)` but defines no lifecycle hooks. `SQLiteCache.__exit__` exists (`caching.py:47`) but is unreachable through the Facade. `CommentAPIClient` owns *another* `httpx.Client`, closed only via `__del__` (`comment_api_client.py:39`) — unreliable at interpreter shutdown and on reference cycles. On Windows the `.db` stays locked. **Fix:** implement `YtMeta.close()`/`__enter__`/`__exit__` that closes the session, the comment client, and the cache; drop the `__del__` hooks.

**H6 — Video-metadata cache key keeps trailing query params, fragmenting cache.** `yt_meta/fetchers.py:108`
`video_id = youtube_url.split("v=")[-1]` so `?v=abc123&t=42s` becomes cache key `video_meta:abc123&t=42s` while `?v=abc123` becomes `video_meta:abc123` — same video cached twice. `VideoFetcher.get_video_id` (line 142) correctly splits on `&`, so the class disagrees with itself. **Fix:** use `utils.extract_video_id` (handles `youtu.be/`, bare IDs, and query params); delete the inferior `get_video_id`.

### Caching / concurrency / security

**H7 — `SQLiteCache` deserializes via `pickle`; tampered DB → RCE.** `yt_meta/caching.py:61`
`pickle.loads(value)` on every read; `pickle.dumps(value)` on every write. The DB path is user-supplied and defaults to `.my_yt_meta_cache/cache.db`. Any party that can write the file — multi-user host, shared volume, accidental commit, malicious tarball — gets arbitrary code execution on next `YtMeta()`. **Fix:** switch to `json`; cached payloads are YouTube JSON dicts (only complication is tuples — convert to lists). If pickle is unavoidable, HMAC-sign the blob and restrict the file mode.

**H8 — `SQLiteCache` is silently single-thread-only.** `yt_meta/caching.py:39`
`sqlite3.connect(self.path)` uses default `check_same_thread=True`. A single `YtMeta` shared across a `ThreadPoolExecutor` or FastAPI handler raises `ProgrammingError`. Also no lock guarding concurrent generator writes. **Fix:** `check_same_thread=False` + `threading.Lock`, or `threading.local` per-thread connections; set `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`.

**H9 — No retry/backoff on transient YouTube errors; `CommentAPIClient(retries=3)` is silently ignored.** `yt_meta/fetchers.py:79`, `yt_meta/comment_api_client.py:33`
Every HTTP call (`_get_continuation_data`, `get_video_metadata`, `_get_channel_page_data`, `_get_raw_playlist_videos_generator`, `CommentAPIClient.make_api_request`) is a single `session.get/post(..., timeout=10)` + `raise_for_status`. No retry on 429/5xx, no backoff, no jitter. `CommentAPIClient.__init__` accepts `retries=3` and never references it again — a test even asserts the attribute, giving false confidence. **Fix:** retry wrapper with exponential backoff + jitter honoring `Retry-After`; wire `retries` through; add `request_delay`.

### Packaging / docs

**H10 — Six "runtime" deps are unused or test-only.** `pyproject.toml:18`
`grep -rn` inside `yt_meta/` shows zero imports of `loguru`, `bs4`, `sqlitedict`, or `youtube_comment_downloader`. `pytest-mock` is a test tool (already duplicated under `[dependency-groups].dev`). `rich` is used only by one example. README + pyproject description still say *"lightweight, dependency-free library"*. CHANGELOG even brags *"native implementation, no external dependencies"* for comments. **Fix:** drop the four unused, move `pytest-mock` to dev, move `rich` to an `examples` extra, fix the description.

**H11 — `tests` package will be shipped in the wheel.** `pyproject.toml:38`
`[tool.setuptools.packages.find] where = ["."]` with no `include`/`exclude`, and `tests/__init__.py` exists — consumers will get an importable top-level `tests` package colliding with their own. **Fix:** `include = ["yt_meta*"]` (or `exclude = ["tests*", "examples*"]`).

**H12 — Default `pytest` invocation hits live YouTube (~25 requests).** `pyproject.toml:41`
`[tool.pytest.ini_options]` registers the `integration` marker but `addopts` doesn't exclude it. So `pytest` (no args) fires integration tests against `@LofiGirl`, `@MrBeast/videos`, `@TED/videos`, etc. Offline CI sees dozens of failures; some asserts are flaky too. **Fix:** `addopts = "-v -m 'not integration'"`; document `pytest -m integration` opt-in.

### Docs accuracy

**H13 — README documents `YtMeta(cache=...)` constructor that doesn't exist.** `README.md:281` / `:439`
Real signature (`client.py:25`) is `__init__(self, cache_path: str | None = None)`. Copy-pasting the README raises `TypeError`. README also claims "Any object implementing the `MutableMapping` protocol works as a cache" — implementation only accepts a path. **Fix:** widen constructor to `cache_path=None, cache=None` and build `SQLiteCache` only when path is given.

**H14 — README `get_video_comments` signature, `filters=`, and `SORT_BY_RECENT` are fabricated.** `README.md:451`
Real signature: `(youtube_url, limit=100, sort_by='top', progress_callback=None, since_date=None)`. There is no `filters` param; `SORT_BY_RECENT`/`SORT_BY_POPULAR` are not exported anywhere. `apply_comment_filters` exists in `filtering.py:235` but has zero callers. **Fix:** either wire `apply_comment_filters` into `CommentFetcher.get_comments`, or rewrite the docs to match reality — don't ship dead code and false docs together.

**H15 — README comment example uses `comment['likes']`; real schema is `like_count`.** `README.md:180`
Snippet raises `KeyError` on every comment. **Fix:** trivial; audit other README examples for the same drift.

### Tests

**H16 — Zero unit tests for the new comment client APIs.** `tests/test_client.py`
`client.py` exposes `get_video_comments`, `get_video_comments_with_reply_tokens`, `get_comment_replies`, and `_resolve_date` (added in `5ea0b62`). `test_client.py` covers metadata/channel paths only; the existing comment tests are integration tests that bypass the client. `_resolve_date`'s date/datetime/relative-string handling has no coverage. **Fix:** mock `_comment_fetcher.get_comments` and assert kwarg conversion for each `since_date` shape; same for `get_comment_replies`.

**H17 — `comment_parser.py` has no fixture-driven tests; 2.4 MB of unused fixtures sit in tree.** `tests/fixtures/comment_continuation_response.json`
551 lines of parser code (`extract_complete_comments`, `parse_comment_complete`, `extract_reply_continuations`) — tests construct synthetic dicts inline. Existing real fixtures are referenced nowhere. `extract_reply_continuations` (which backs the new reply-token API) is completely untested. **Fix:** wire fixtures into `test_comment_fetcher.py`; assert representative comments (id, author, like_count, reply_count, is_pinned).

---

## Medium severity

Tighter list — refer to file:line for details:

- **M1** Comment subsystem ignores `YtMeta`'s shared session and cache; duplicates watch-page fetches with different headers — `comment_fetcher.py:28`, `comment_api_client.py:33`.
- **M2** `parse_video_renderer` crashes on `metadataBadgeRenderer: None` (defaults only apply to *missing* keys) — `parsing.py:389`.
- **M3** `extract_shorts` indexes `[0][0]` without checking; in-feed ads → `IndexError` kills shorts generator — `fetchers.py:375`.
- **M4** `publish_date` type drift: `parse_video_renderer` returns `datetime`, `parse_video_metadata` returns ISO string; merge replaces the former — `parsing.py:529`.
- **M5** `validate_filters` runs *before* the date-filter rewrite in both channel and playlist paths — `fetchers.py:418`, `:592`. (This is what let H1 ship.)
- **M6** `apply_filters` silently drops videos when a fast-filter field is missing — `filtering.py:208`.
- **M7** `get_video_metadata` returns `None` on parse failure despite `-> dict` annotation and a docstring that promises raising — `fetchers.py:134`.
- **M8** `YtMetaError` base class is defined but not exported; README error-handling section references a class users can't import — `__init__.py:12`.
- **M9** Identifier kwargs inconsistent across the public surface (`youtube_url` / `video_id` / `channel_url` / `playlist_id`) — `client.py:69`.
- **M10** Single global 86,400 s TTL applied to immutable video metadata and fast-changing channel listings alike; not surfaced on `YtMeta` — `caching.py:35`, `client.py:35`.
- **M11** Channel-page cache stores raw HTML alongside parsed structures, bloating the DB ~3× — `fetchers.py:201`.
- **M12** `__del__` hooks on `CommentAPIClient`/`CommentFetcher` are unreliable cleanup — `comment_api_client.py:39`.
- **M13** SSRF risk: `channel_url` fetched without host validation; `extract_video_id` has a permissive pass-through fallback — `fetchers.py:182`, `utils.py:96`.
- **M14** Internals `CommentAPIClient`, `CommentParser`, `BestCommentFetcher` re-exported as public; `BestCommentFetcher` has no `DeprecationWarning` — `__init__.py:4`.
- **M15** Version drift: `__init__.py` + `pyproject` say `0.3.1`; CHANGELOG announces `2.0.0` for this code — `__init__.py:10`.
- **M16** README references `yt-meta[persistent_cache]` extra that isn't declared in pyproject — `README.md:33`, `:268`.
- **M17** `VideoFetcher.get_video_id` reimplements `utils.extract_video_id` worse — no `youtu.be/` support, so `client.get_video_comments('https://youtu.be/...')` raises — `fetchers.py:140`.
- **M18** README "Library Architecture" claims `VideoFetcher` "fetches metadata *and comments*" and that `YtMeta` "inherits from `youtube-comment-downloader`" — both false — `README.md:502`, `:441`.
- **M19** `apply_comment_filters` is dead code; README documents comment filtering that doesn't work — `filtering.py:235`, `README.md:311`.
- **M20** Transcript tests only verify `MagicMock` plumbing; language-fallback and `NoTranscriptFound` paths untested; bare `except Exception` swallows everything — `tests/test_transcript_fetcher.py:9`, `transcript_fetcher.py:35`.
- **M21** Channel-fetcher tests mock private symbols (`_get_channel_page_data`, `_get_continuation_data`); refactors silently break tests — `tests/test_channel_fetcher.py:33`.
- **M22** `test_apply_filters_publish_date` uses `after`/`before` operators that aren't in `FILTER_SCHEMA` — bypassing the validator masks the documentation gap — `tests/test_filtering.py:336`.
- **M23** `comment_fetcher` catches bare `Exception` and re-raises as `VideoUnavailableError`, so any `KeyError`/`TypeError` from a code change reports as "video unavailable"; test reinforces the broken contract — `comment_fetcher.py:154`.

---

## Architecture observations

1. **Facade is the right shape but leaks resources.** `YtMeta` owns two `httpx.Client`s (main session + `CommentAPIClient`'s private one) and a SQLite connection, yet exposes no `close()`/context-manager. `SQLiteCache` implements the protocol but it's unreachable through the Facade. → file descriptors, sockets, and a Windows-locked `.db` persist for the process lifetime.

2. **Comment subsystem is architecturally siloed.** Builds its own `httpx.Client` with different headers (`User-Agent`, `follow_redirects=True` vs. the main session's `Accept-Language`), ignores `SQLiteCache`, and duplicates `ytcfg`/`initialData` parsing that already exists in `parsing.py`. The README claim that the Facade "holds shared objects like the session and cache" is **false** for this path.

3. **Date/filter handling is fragmented across three call sites with three DSL shapes.** ChannelFetcher uses dict-shaped `{'gte':…, 'lte':…}`; PlaylistFetcher invented an incompatible tuple shape that crashes the pipeline (H1); `get_channel_shorts` has no `start_date`/`end_date` kwargs at all. `validate_filters` runs *before* the rewrite, so bad shapes slip past. A single `_build_date_filter` helper + post-rewrite validation would eliminate an entire class of bugs.

4. **`_BaseFetcher` hides a missing abstraction.** Shares two methods between `Channel`/`PlaylistFetcher`; `VideoFetcher` doesn't inherit it. Meanwhile the *real* common logic (`partition_filters` + `fetch_full_metadata` + the `_process_videos_generator` epilogue) is hand-duplicated across `get_channel_videos`, `get_channel_shorts`, `get_playlist_videos`. Inheritance hides duplication rather than expressing it.

5. **Public surface is inconsistent.** Identifier kwargs vary (`youtube_url` / `video_id` / `channel_url` / `playlist_id`); `VideoFetcher.get_video_id` reimplements `utils.extract_video_id` worse (no `youtu.be/`); `CommentAPIClient` and `CommentParser` are re-exported despite being implementation details; `BestCommentFetcher` alias has no deprecation warning.

6. **Tests over-rely on private-symbol mocking.** `_get_channel_page_data`, `_get_continuation_data`, `_get_raw_playlist_videos_generator` are patched rather than mocking at the HTTP layer with `respx` / `httpx.MockTransport`. Refactors silently break tests, and ~2.4 MB of comment/playlist fixture JSON sits unused. Newest subsystems (comments, transcripts) have the weakest coverage.

7. **Resilience primitives are missing across the board.** No retry/backoff (despite an accepted-and-ignored `retries=3` param), no rate limiting, no per-call timeout configuration, single global 86,400 s TTL applies to immutable video metadata *and* fast-changing channel listings, `force_refresh` doesn't propagate past page 1, and `sqlite3.connect` uses default `check_same_thread=True` (so the Facade is silently single-thread-only).

---

## Quick wins (low-effort, high-value)

- Drop `loguru`, `beautifulsoup4`, `sqlitedict`, `youtube-comment-downloader` from `[project.dependencies]` — none are imported in `yt_meta/`.
- Move `pytest-mock` from `[project.dependencies]` to `[project.optional-dependencies].dev` (already duplicated there).
- Add `include = ["yt_meta*"]` (or `exclude = ["tests*", "examples*"]`) under `[tool.setuptools.packages.find]` to stop shipping `tests/` in the wheel.
- Add `addopts = "-v -m 'not integration'"` to `[tool.pytest.ini_options]` so default `pytest` runs offline.
- Fix `README.md:180` — change `comment['likes']` → `comment['like_count']`.
- Add `YtMetaError` to `__all__` and imports in `yt_meta/__init__.py`.
- Delete the dead `mocked_client` / `client_with_caching` fixtures in `tests/test_client.py:16-37` — they patch `yt_meta.client.requests.Session` and the package uses `httpx`.
- Reconcile version: bump `__init__.py` + `pyproject.toml` to 0.4.0 / 1.0.0 to match CHANGELOG features, *or* correct the CHANGELOG heading.
- Remove the empty `[tool.ruff]` placeholder (`# ... existing code ...`) at `pyproject.toml:57-59`.
- Add per-Python-minor classifiers (3.10/3.11/3.12/3.13), OS classifier, `Development Status`, and Repository/Issues/Changelog URLs to `pyproject.toml`.
- Add empty `yt_meta/py.typed` marker and list it under `[tool.setuptools.package-data]` so downstream type-checkers pick up existing hints.
- Modernize types: `from typing import Dict, List` → built-in generics (`list[dict]`, `list[str] | None`); the codebase is already 3.10+.
- `parsing.py:97` — return `total_seconds if duration_label else None` so 0-second durations are preserved instead of collapsing to `None`.
- Normalize `final_start_date`/`final_end_date` to `date` around `fetchers.py:319` to prevent `TypeError` when the user passes `datetime.now()`.
- Remove dead `if not continuation_data: break` at `fetchers.py:326`, `:383` (`_get_continuation_data` never returns `None`), or wrap the HTTP call in try/except so transient 5xx doesn't kill iteration.
- Remove dead `stop_pagination = False` in `_get_raw_shorts_generator` (`fetchers.py:366`).
- Remove `pytz` from runtime deps — already noted as transitive via `dateparser` in the inline comment.

---

## Longer-term improvements

1. **Unify the date-filter pipeline.** Introduce `_build_date_filter(start, end) -> dict`, use it from every call site (channel videos, channel shorts, playlists, future paths), run `validate_filters` *after* the rewrite, and tighten `parse_relative_date_string` to fail loudly. Together this eliminates an entire bug class (H1, H2, M5, M6).

2. **Unify the comment subsystem under shared Facade resources.** Refactor `CommentAPIClient` and `CommentFetcher` to accept `session: httpx.Client` and `cache: MutableMapping` from `YtMeta`, share watch-page extraction with `VideoFetcher` (single `video_initial:{video_id}` cache entry), share `ytcfg`/`initialData` regexes with `parsing.py`, and replace `__del__` with explicit `close()`/context-manager lifecycle. Doubles caching efficiency for mixed metadata+comments workflows, aligns header behavior, fixes the leak.

3. **Build proper resilience primitives.** Reusable retry/backoff wrapper (tenacity or in-house) honoring `Retry-After`, exponential backoff with jitter, per-call timeouts, optional shared rate limiter, and wire `CommentAPIClient.retries` through. Plumb `force_refresh` into `_get_continuation_data` so "fresh" actually means fresh across pages.

4. **Make `YtMeta` a real context manager and rationalize caching.** Add `close()`/`__enter__`/`__exit__` (closes session, comment client, cache); add per-prefix TTL on `SQLiteCache` (lengthen lifetimes for immutable prefixes like `video_meta:` relative to today's 86,400 s default, keep volatile prefixes like `channel_page:` at the current TTL or shorter — net effect is **fewer** refreshes, not more); open with `check_same_thread=False` + `threading.Lock` + WAL mode; drop raw HTML from cached channel-page tuples; replace `pickle` with `json` to close the RCE vector.

5. **Replace inheritance with composition for fetchers.** `_BaseFetcher` saves two methods; the real duplication is the `partition_filters` → `fetch_full_metadata` → `_process_videos_generator` epilogue hand-copied across three call sites. Extract `_run_filtered_pipeline(filters, content_type, raw_generator, ...)`; let `_BaseFetcher` go.

6. **Invest in real test infrastructure for comments + transcripts.** Wire the existing 2.4 MB of unused fixtures into fixture-driven parser tests. Replace `MagicMock`-based transcript tests with recorded JSON + `respx`. Add end-to-end `ChannelFetcher` tests that exercise the real continuation loop via `httpx.MockTransport` instead of patching private methods. Use `freezegun` for date-utils tests. Tighten the broad `except Exception` in `comment_fetcher` to specific httpx errors.

7. **Strict input validation at the network boundary.** Whitelist hostnames before issuing channel/playlist requests; validate `video_id` against `^[A-Za-z0-9_-]{11}$` (drop the pass-through fallback in `extract_video_id`); scrub `INNERTUBE_API_KEY` from any logged URL (sanitize log output only; do not change the request shape — the library uses the same internal innertube endpoint and public web key as YouTube's own JS, **not** the official YouTube Data API, and that should stay); cap input size or use a streaming brace-matcher in place of the catastrophic-backtracking-prone `YT_INITIAL_DATA_RE` regex.

---

**Notes on what was dropped:** synthesis filtered ~16 lower-signal items (catastrophic-backtracking regexes today only run on `youtube.com`-controlled payloads; `INNERTUBE_API_KEY` in logs is public; `force_refresh` propagation bug folded into longer-term #4; etc.). Full per-lens reports and dropped list are in the workflow output JSON at `/tmp/claude-1001/-workspace/62452a06-dbc7-4fb7-9e29-265959fdff68/tasks/w9hdwct1q.output` if you want to audit what was filtered.

---

## Suggested roadmap

Severity ranking tells you which fix is most urgent in isolation; it doesn't tell you which fixes batch well together or which release each cluster belongs to. This roadmap groups the 40 findings into **six themes** anchored on the project's own stated values (minimal requests, native implementation, fail-fast validation, Facade pattern) plus three orthogonal axes (release readiness, security/leaks, comment-subsystem rehab), and sequences them across **three releases**.

### The six themes

**T1 — "Make the documented API runnable"** (release-blocker)
The README has multiple snippets that raise `TypeError` / `KeyError` / `AttributeError` on copy-paste, and the codebase has bugs in documented kwargs. Fix what new users hit first.
- **H1** playlist `start_date`/`end_date` tuple-filter crash (`fetchers.py:596`)
- **H2** `parse_relative_date_string` silent-today fallback (`date_utils.py:57`)
- **H13** `YtMeta(cache=...)` constructor doesn't exist (`README.md:281`, `client.py:25`)
- **H14** `get_video_comments` signature / `SORT_BY_RECENT` / `filters=` fabricated (`README.md:451`)
- **H15** `comment['likes']` → `comment['like_count']` (`README.md:180`)
- **M15** version drift (`__init__.py` 0.3.1 vs CHANGELOG 2.0.0)
- **M16** `yt-meta[persistent_cache]` extra not declared in pyproject
- **M17** `VideoFetcher.get_video_id` breaks `youtu.be/` URLs (`fetchers.py:140`)
- **M18** README architecture section misdescribes `VideoFetcher` and claims false inheritance
- **M19** `apply_comment_filters` dead code; comment filters documented but not wired

**T2 — "Honor minimal requests"** (the project's flagship value)
Each fix in this theme directly reduces the number of HTTP calls.
- **M1** comment subsystem ignores `YtMeta`'s shared session and cache; duplicate watch-page fetches
- **H6** video-metadata cache key fragmentation (`fetchers.py:108`)
- **M11** channel-page cache stores raw HTML alongside parsed structures (3× bloat)
- **H12** default `pytest` fires ~25 live YouTube requests (`pyproject.toml:41`)
- **M10** single global TTL — setup for Longer-term #4
- Quick win: propagate `force_refresh` past page 1 (`fetchers.py:325`)
- **Longer-term #2** unify comment subsystem under shared resources
- **Longer-term #4** per-prefix TTL (lengthen immutable prefixes)

**T3 — "Honor native implementation"** (the CHANGELOG's "no external dependencies" claim)
Match the shipped artifact to the stated principle.
- **H10** drop `loguru`, `beautifulsoup4`, `sqlitedict`, `youtube-comment-downloader`, `pytest-mock`, `rich` from runtime deps
- **H11** exclude `tests/` from the wheel (`pyproject.toml:38`)
- Quick wins: classifiers, `py.typed` marker, project URLs, remove empty `[tool.ruff]` placeholder, drop transitive `pytz`
- **M15** version reconcile (also appears in T1)

**T4 — "Plug leaks"** (security + resource hygiene)
Bugs that survive normal use but bite in production / under load / on tampered input.
- **H7** `pickle` in `SQLiteCache` → RCE on tampered DB
- **H5** `YtMeta` has no `close()` / `__enter__` / `__exit__`; `httpx.Client` + SQLite leak
- **H8** `SQLiteCache` silently single-thread-only
- **H9** no retry/backoff; `CommentAPIClient(retries=3)` silently ignored
- **M12** `__del__` hooks on `CommentAPIClient`/`CommentFetcher` unreliable
- **M13** SSRF: `channel_url` fetched without host validation; `extract_video_id` pass-through fallback
- **Longer-term #7** strict input validation at the network boundary

**T5 — "Rehab the comment subsystem"** (the newest code = the most concentrated debt)
Almost every comment-area finding belongs here; treating them together makes the refactor coherent.
- **H3** continuation-token DFS picks up reply tokens → silent truncation
- **H4** pagination breaks on first all-duplicate page
- **H16** zero unit tests for the new client comment APIs
- **H17** `comment_parser.py` has no fixture-driven tests; 2.4 MB of unused fixtures
- **M14** internals `CommentAPIClient`, `CommentParser`, `BestCommentFetcher` re-exported as public
- **M20** transcript tests + comment broad `except Exception` (**M23**) — folded in because they share the same "newest code" pattern
- **Longer-term #2** unify comment subsystem under shared resources (also appears in T2 — load-bearing refactor)
- **Longer-term #6** invest in real test infrastructure for comments + transcripts

**T6 — "Reduce architectural strain"** (the long refactors)
Things that aren't bugs but make the code expensive to evolve.
- Architecture observation #3 + **Longer-term #1** unify the date-filter pipeline (`_build_date_filter`)
- Architecture observation #4 + **Longer-term #5** replace `_BaseFetcher` inheritance with composition (`_run_filtered_pipeline`)
- Architecture observation #5 + **M9** identifier-kwarg consistency
- **M5** `validate_filters` runs before date-filter rewrite (root cause of H1)
- **M6** `apply_filters` silently drops videos when fast-filter field is missing
- **M7** `get_video_metadata` returns `None` despite `-> dict` contract
- **M4** `publish_date` type drift between renderer and metadata paths
- **M2**, **M3** defensive parsing crashes
- **M8** export `YtMetaError`
- **M21** channel-fetcher tests mock private symbols
- **M22** `test_apply_filters_publish_date` uses operators not in `FILTER_SCHEMA`

### The three-release sequence

The whole roadmap stays under 1.0. **0.6.0 is the explicit terminal release from this work** — after it ships, the project sits at a stable pre-1.0 line and a future 1.0.0 is a separate decision out of scope here. Pre-1.0 semver permits all breaking changes below in minor bumps, but each break is flagged in CHANGELOG because users care about churn even when semver allows it.

#### v0.4.0 — "Make the docs match the code" (T1 + the README/version slice of T3)

Smallest set, fastest to ship, biggest user-visible win. README becomes copy-pasteable; `pip install yt-meta` no longer drags ~20 MB of unused deps. Includes H1/H2 because they're documented-API correctness bugs, not design changes. Reconcile the version to 0.4.0 as part of the release; relabel the existing `## [2.0.0] - 2024-07-03` CHANGELOG entry to `## [0.4.0]` since those changes (transcript + comment overhaul) ship in the 0.3.1 codebase that this release supersedes.

| Marker | Item |
|---|---|
| **BREAKING** | **H2** — `parse_relative_date_string` raises `ValueError` on unrecognized input (was silently returning today). |
| **BREAKING** | **H10** (partial) — removes `loguru`, `beautifulsoup4`, `sqlitedict`, `youtube-comment-downloader` from runtime deps. Environments that consumed them transitively must install them explicitly. |
| **DEPRECATED** | **M14** — `BestCommentFetcher`, top-level `CommentAPIClient`/`CommentParser` re-exports emit `DeprecationWarning`. Removal in 0.6.0. |
| **DEPRECATED** | **M17** — `VideoFetcher.get_video_id` warns and delegates to `utils.extract_video_id`. Removal in 0.6.0. |
| Additive | All README fixes (H13–H15, M16, M18), M19 decision (delete dead `apply_comment_filters` or wire it), H1 playlist date-filter fix, M15 version reconcile. |

#### v0.5.0 — "Honor the values" (T2 + remaining T3 + T4 minus the deep refactors)

The values-payoff release. Each fix here directly reinforces a stated principle and the bundle composes cleanly. The codebase starts matching its own self-description.

| Marker | Item |
|---|---|
| **BREAKING** | **H7** — `SQLiteCache` switches from `pickle` to `json`. Existing `.my_yt_meta_cache/cache.db` files are unreadable. Detect-and-refuse migration: on open, if the schema/header indicates the old pickle format, raise a clean one-line error ("yt-meta 0.5 changed the on-disk cache format; delete `<path>` to rebuild") and exit. No silent rebuild — explicit user action. |
| **BREAKING** | **H12** — default `pytest` no longer hits live YouTube. CI configs that depended on integration tests running by default must add `-m integration`. |
| Additive | H5 `close()`/`__enter__`/`__exit__`, H8 thread safety + WAL, H9 retry/backoff, H6 cache-key fix, M1 (load-bearing part of L2) comment subsystem shares session/cache, M11 drop raw HTML from cached channel pages, M10 expose `cache_ttl_seconds`, H11 exclude `tests/` from wheel, `force_refresh` propagation, M12/M13 hygiene. |

#### v0.6.0 — "Pay down the debt" (T5 + T6) — **terminal release from this roadmap**

The deep work. Clears the deprecations introduced in 0.4.0; ships the long refactors. After this, the project is at a stable pre-1.0 line.

| Marker | Item |
|---|---|
| **BREAKING** | **M14** final — re-exports removed from `__init__.py`. The 0.4.0 `DeprecationWarning` becomes an `ImportError`. |
| **BREAKING** | **M17** final — `VideoFetcher.get_video_id` removed. |
| **BREAKING** | **H3/H4** — comment continuation rewrite returns more results than the buggy version did. Observably different (bug fix, but visible). |
| **DEPRECATED** | **M9** — identifier-kwarg standardization shipped with aliases. Old names (`youtube_url`, `channel_url`, etc.) warn but still work. Removal deferred past this roadmap. |
| Additive | `_build_date_filter` helper (kills the H1/M5/M6 bug class), `_run_filtered_pipeline` (retires `_BaseFetcher`), fixture-driven parser tests using the existing 2.4 MB of unused fixtures, per-prefix TTL on `SQLiteCache`, M2/M3/M4/M7/M8 robustness, M20–M23 test improvements, `__del__` hooks retired. |

### Why this framing

Severity-only ranking tells you which fix is most urgent in isolation but not which fixes batch well together. Subsystem-first grouping (by file) is mechanical, easy to act on, but doesn't tell a story to a reviewer or a CHANGELOG reader. Cost-to-fix is a fine sequencing heuristic but doesn't explain *why* a batch matters. Values-anchored themes + a release sequence give each theme a sentence you can put in a release note and let the project's own stated principles drive the priorities. Capping at 0.6.0 keeps the whole roadmap under 1.0 and leaves the 1.0 declaration as a future, separate decision.
