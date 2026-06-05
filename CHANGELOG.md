# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

- (Add new changes here)

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
