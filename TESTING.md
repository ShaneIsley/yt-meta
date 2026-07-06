# Testing rules

Adopted 2026-07-05, alongside the 0.8.0 release. The project was built
test-first, yet the 2026-07-05 review found eight bugs that the tests
should have caught. Each traces to the same root cause, and the rules
below target it.

## Why TDD didn't catch these

TDD guarantees the code satisfies the tests. It says nothing about
whether the tests describe reality. Every escaped bug came from a
false model of something external, shared by the code and its test:
when the same author writes both from the same wrong assumption,
red/green passes and the bug ships.

| Bug (2026-07-05 review) | The false model | How the test missed it |
|---|---|---|
| Comment filters `channel_id`/`is_by_owner`/`is_hearted_by_owner` never match (C1) | Filter layer assumed a comment-dict vocabulary the parser doesn't emit | Tests filtered hand-written dicts using the filter layer's vocabulary; real parser output never flowed through `apply_comment_filters` |
| `except httpx.RequestError` misses 4xx/5xx (C2) | Assumed `HTTPStatusError` subclasses `RequestError` | Tests mocked at the method level; `raise_for_status()` never raised a real httpx exception in any test |
| `limit=-1` yields zero comments (C4) | — | Docstring promised `-1` works; tests covered only the guard's raise path, not the documented success path |
| Past streams get `publish_date=None` (C7) | Assumed dateparser handles "Streamed 2 days ago" | The streams fixture contained only scheduled items; the completed-stream state was never captured |
| Status tracking loses content on 2nd consecutive "unavailable" (M-b) | — | Stateful logic tested with single transitions (ok→unavailable); the repeating-state sequence was never driven |
| Selective filters truncate pagination (C5) | — | Filters and the empty-page counter were each tested alone; their interaction had no test |
| SQLite cache turns `datetime` into `str` (M-a) | `json.dumps(default=str)` assumed all cache shapes are JSON-safe | Cache tested with toy values, fetchers with dict caches; no test round-tripped a real payload through the real cache |
| Reply pagination misses button-form tokens (M-c) | Assumed one continuation-token shape | The reply fixture was a 953-byte hand-built stand-in for YouTube's response |

Three patterns cover all eight:

1. Hand-written test data encodes the author's assumptions (C1, C7, M-c, M-a).
2. Mocks simulate dependencies from memory instead of exercising them (C2).
3. Coverage tracks what the author thought about, not what was promised or possible (C4, M-b, C5).

## The rules

**R1 — Boundary tests consume real upstream output.** A test for layer
N feeds it the actual output of layer N-1: run the real parser on a
captured fixture; exercise HTTP handling through `httpx.MockTransport`
with real status codes. Do not hand-write the input dict for a layer
that has a real producer, and do not raise a dependency's exception
from a mock. Let the dependency raise it.

**R2 — Vocabulary contracts get a pinning test.** Wherever one module
consumes keys another module emits (filter keys vs. parser output,
cache keys, dict schemas), a contract test asserts the consumed
vocabulary is a subset of the produced one, using real parser output
from a captured fixture. Drift on either side then fails the suite.

**R3 — Docstring promises are test cases.** Every input shape, special
value, or behavior a docstring or the README documents gets a test in
the same commit that documents it.

**R4 — Audit the fixture state space.** When upstream has enumerable
states (scheduled/live/completed streams; first/continuation pages;
ok/unavailable videos), list them in the test module docstring and
either cover each with a fixture or waive it with a reason.

**R5 — Stateful logic gets sequence tests.** Anything that reads its
own prior output (status tracking, pagination cursors, dedup sets) is
tested over sequences of three or more steps, including repeated
states, not just single transitions.

**R6 — Interacting features get an interaction test.** When a feature
adds a condition to a loop another feature also controls (filters ×
pagination, cache × force_refresh), add at least one test with both on.

**R7 — No silent serialization fallbacks.** `default=str` and similar
convert type errors into corrupted data. Encode known non-JSON types
explicitly and let unknown types raise. Round-trip tests use a
representative real payload, not toy values.

**R8 — Every bug fix ships a REGRESSION-marked test** that fails on the
pre-fix code and passes after.

**R9 — Mark synthetic fixtures.** When a real capture is impossible,
mark the fixture as synthetic or derived in its filename or the test
docstring, and pair it with a live `-m contract` assertion covering the
same behavior, so the live suite validates what the unit suite cannot.
