import inspect
from datetime import date
from unittest.mock import Mock, patch

import pytest

from yt_meta.comment_fetcher import BestCommentFetcher, CommentFetcher
from yt_meta.exceptions import VideoUnavailableError


def test_h14_default_sort_for_comment_fetcher_get_comments_is_recent():
    """H14 (default-sort half): CommentFetcher.get_comments defaults sort_by
    to 'recent' so since_date short-circuits work out of the box and the raw
    chronological stream is returned by default (yt-meta is a
    metadata-retrieval tool; YouTube's 'Top' ranking is editorial, not raw
    data).
    """
    sig = inspect.signature(CommentFetcher.get_comments)
    assert sig.parameters["sort_by"].default == "recent"


def test_h17_extract_complete_comments_from_real_fixture(
    comment_continuation_response,
):
    """REGRESSION (H17 / L6): comment_parser.py was 551 lines of code
    covered exclusively by synthetic in-line dict stubs. Meanwhile a
    real 622 KB captured API response sat unused in
    ``tests/fixtures/comment_continuation_response.json``. v0.6.0
    wires the fixture in so the parser is exercised against an actual
    YouTube payload shape — the kind of shape future YouTube changes
    will quietly break.
    """
    from yt_meta.comment_parser import CommentParser

    parser = CommentParser()
    comments = parser.extract_complete_comments(comment_continuation_response)

    # The fixture contains 20 top-level comments (verified during the
    # M19 / minimal-requests analysis where we walked the same file).
    assert len(comments) == 20

    # Every comment has the canonical fields with the canonical types
    # — guards against silent shape changes (e.g. like_count flipping
    # back to str).
    for c in comments:
        assert isinstance(c["id"], str) and c["id"]
        assert isinstance(c["author"], str)
        assert isinstance(c["text"], str)
        assert isinstance(c["like_count"], int)
        assert isinstance(c["reply_count"], int)
        assert isinstance(c["is_reply"], bool)

    # IDs unique within the page — protects against the deduplication
    # logic in CommentFetcher (seen_ids set) accidentally relying on
    # the parser uniquifying.
    ids = [c["id"] for c in comments]
    assert len(set(ids)) == len(ids), "fixture contains duplicate ids"

    # Spot-check known values from the fixture (these come from the
    # actual captured page — see the M19 walkthrough that enumerated
    # 4 distinct publish times and like counts ranging 5-412).
    like_counts = [c["like_count"] for c in comments]
    assert max(like_counts) >= 400  # the 412-like comment is in there
    assert min(like_counts) >= 0


def test_reply_token_subthreads_shape():
    """REGRESSION: YouTube moved the reply-continuation token from
    ``commentRepliesRenderer.contents[]`` to
    ``commentRepliesRenderer.subThreads[]``. extract_reply_continuations
    only checked ``contents``, so it returned an empty mapping against
    live data — comments with hundreds of replies surfaced no
    reply_continuation_token. Captured from a live "Me at the zoo"
    response (3 threads, all with subThreads tokens)."""
    import json
    from pathlib import Path

    from yt_meta.comment_parser import CommentParser

    fixture = (
        Path(__file__).parent / "fixtures" / "comment_threads_subthreads.json"
    )
    with open(fixture) as f:
        response = json.load(f)

    tokens = CommentParser().extract_reply_continuations(response)
    # All 3 threads in the fixture have replies → all 3 must yield tokens.
    assert len(tokens) == 3, (
        f"expected 3 reply tokens from the subThreads shape, got {len(tokens)}"
    )
    for comment_id, token in tokens.items():
        assert comment_id.startswith("Ug")  # real YouTube comment id
        assert isinstance(token, str) and len(token) > 10


def test_l6_extract_reply_continuations_from_real_fixture(
    comment_continuation_response,
):
    """REGRESSION (L6): extract_reply_continuations is the backbone of
    the reply-token API path (client.get_video_comments_with_reply_tokens
    and client.get_comment_replies) and was completely untested.
    Verify it produces a comment_id → reply_token mapping on a real
    payload.
    """
    from yt_meta.comment_parser import CommentParser

    parser = CommentParser()
    reply_tokens = parser.extract_reply_continuations(
        comment_continuation_response
    )

    assert isinstance(reply_tokens, dict)
    # If the captured page has threads with replies, we should pick up
    # at least one mapping. The fixture had 10 replies on the top
    # comment, so the count is non-zero.
    assert len(reply_tokens) > 0, (
        "expected at least one reply_continuation_token in the fixture"
    )
    # Every key is a comment id present in the same fixture's comments
    parser2 = CommentParser()
    comment_ids = {
        c["id"] for c in parser2.extract_complete_comments(comment_continuation_response)
    }
    for comment_id in reply_tokens:
        assert comment_id in comment_ids, (
            f"reply token for {comment_id!r} but no matching comment"
        )
    # Every value is a non-empty string token
    for token in reply_tokens.values():
        assert isinstance(token, str) and len(token) > 10


def test_m1_l2_comment_api_client_uses_injected_session():
    """REGRESSION (M1/L2): CommentAPIClient used to build its own
    httpx.Client with its own (different) headers and follow_redirects
    setting. YtMeta then ended up owning TWO clients side by side and
    needed to close both via the lifecycle work (H5). M1/L2 closes the
    loop: CommentAPIClient now accepts an injected session and uses it
    instead of constructing its own. YtMeta passes its main session in,
    so there's one client end-to-end.
    """
    import httpx

    from yt_meta.comment_api_client import CommentAPIClient

    injected = httpx.Client()
    try:
        client = CommentAPIClient(session=injected)
        assert client.client is injected
    finally:
        injected.close()


def test_m1_l2_comment_api_client_does_not_close_injected_session():
    """REGRESSION (M1/L2): with an injected session, close() must NOT
    close it — the injector owns the lifecycle. Closing it would tear
    down the main YtMeta session out from under the other fetchers.
    Self-owned sessions (no injection) ARE closed.
    """
    import httpx

    from yt_meta.comment_api_client import CommentAPIClient

    injected = httpx.Client()
    try:
        client = CommentAPIClient(session=injected)
        client.close()
        assert not injected.is_closed, (
            "close() must not tear down an injected session — that's the "
            "injector's responsibility"
        )

        # Self-owned session: close() should close it.
        own = CommentAPIClient()
        owned_client = own.client
        own.close()
        assert owned_client.is_closed
    finally:
        injected.close()


def test_m1_l2_comment_api_client_uses_injected_cache():
    """REGRESSION (M1/L2): CommentAPIClient bypassed YtMeta's cache
    entirely — fetching the watch page for comments duplicated the
    fetch VideoFetcher had already done for metadata. Now both share
    the same cache and the same key prefix (``video_initial:{video_id}``).
    A mixed metadata+comments workflow halves its watch-page fetches.
    """
    from yt_meta.comment_api_client import CommentAPIClient

    cache: dict = {}
    client = CommentAPIClient(cache=cache)
    try:
        assert client.cache is cache
    finally:
        client.close()


def test_m1_l2_get_initial_video_data_caches_under_shared_key(mocker):
    """REGRESSION (M1/L2): get_initial_video_data writes its parse
    result under ``video_initial:{video_id}`` — same key VideoFetcher
    can read (or write). First call fetches, second call hits cache.
    """
    from yt_meta.comment_api_client import CommentAPIClient

    cache: dict = {}
    client = CommentAPIClient(cache=cache)
    try:
        mock_response = mocker.MagicMock()
        mock_response.text = (
            '<script>ytcfg.set({"INNERTUBE_API_KEY":"k","INNERTUBE_CONTEXT":{}});</script>'
            '<script>var ytInitialData = {"hello":"world"};</script>'
        )
        mock_response.raise_for_status = mocker.MagicMock()
        get_mock = mocker.patch.object(
            client.client, "get", return_value=mock_response
        )

        # First call fetches and populates cache under the shared key
        initial_data, ytcfg = client.get_initial_video_data("dQw4w9WgXcQ")
        assert initial_data == {"hello": "world"}
        assert ytcfg["INNERTUBE_API_KEY"] == "k"
        assert get_mock.call_count == 1
        assert "video_initial:dQw4w9WgXcQ" in cache

        # Second call: cache hit, no HTTP call
        initial_data2, ytcfg2 = client.get_initial_video_data("dQw4w9WgXcQ")
        assert initial_data2 == initial_data
        assert ytcfg2 == ytcfg
        assert get_mock.call_count == 1, "second call should hit cache, not network"
    finally:
        client.close()


def test_m1_l2_ytmeta_shares_session_and_cache_with_comment_fetcher(tmp_path):
    """REGRESSION (M1/L2): the integration point. YtMeta now passes
    self.session and self.cache into the CommentFetcher constructor so
    there's a single session and a single cache across the whole
    Facade. Validates the wiring end-to-end.
    """
    from yt_meta import YtMeta

    with YtMeta(cache_path=str(tmp_path / "cache.db")) as client:
        assert client._comment_fetcher.api_client.client is client.session
        assert client._comment_fetcher.api_client.cache is client.cache


def test_m23_comment_fetcher_does_not_swallow_unexpected_exceptions(mocker):
    """REGRESSION (M23): comment_fetcher.py's outer
    ``except Exception as e: ... raise VideoUnavailableError(...)`` would
    convert ANY error inside the comment loop — KeyError, TypeError
    from a code change in extract_complete_comments, even a programmer
    bug — into "video unavailable", misleading users about the actual
    cause. Tighten to httpx-level errors and let the rest surface.

    M1/L2 lands the same fix because the broad except sat on the path
    that's being restructured for cache integration.
    """
    fetcher = CommentFetcher()
    mocker.patch.object(
        fetcher.api_client,
        "get_initial_video_data",
        side_effect=KeyError("programmer bug — not a network/availability issue"),
    )

    # KeyError must surface as KeyError, not get wrapped as
    # VideoUnavailableError.
    with pytest.raises(KeyError):
        list(fetcher.get_comments("dQw4w9WgXcQ"))


def test_h3_extract_continuation_token_returns_next_page_not_reply_token():
    """REGRESSION (H3): extract_continuation_token did a free-form DFS
    over the whole API response, returning the first
    ``continuationCommand.token`` that ``_is_comment_token`` accepted.
    ``_is_comment_token`` accepted any token containing the substring
    'replies' (line 224). YouTube comment responses embed reply
    continuation tokens INSIDE per-thread ``commentRepliesRenderer``
    structures, which DFS visits before reaching the top-level next-
    page token. The function silently returned a reply token instead
    of the next-page token; the next API call fetched replies for an
    already-seen thread; every id was already in seen_ids; the
    (pre-H4) ``if not found_comments: break`` fired; the comment
    stream was silently truncated.

    Fix walks the documented path explicitly:
    onResponseReceivedEndpoints[*].(reloadContinuationItemsCommand|
    appendContinuationItemsAction).continuationItems[-1]
    .continuationItemRenderer.continuationEndpoint.continuationCommand
    .token — that's where YouTube actually puts the next-page token.
    Reply tokens are nested deeper and never picked up.
    """
    from yt_meta.comment_api_client import CommentAPIClient

    api_response = {
        "onResponseReceivedEndpoints": [
            {
                "reloadContinuationItemsCommand": {
                    "continuationItems": [
                        # A comment thread with a nested reply continuation
                        # — this token MUST NOT be returned.
                        {
                            "commentThreadRenderer": {
                                "replies": {
                                    "commentRepliesRenderer": {
                                        "contents": [
                                            {
                                                "continuationItemRenderer": {
                                                    "continuationEndpoint": {
                                                        "continuationCommand": {
                                                            "token": "REPLY_TOKEN_4qmFsgI_replies_NESTED",
                                                            "request": "CONTINUATION_REQUEST_TYPE_WATCH_NEXT",
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                        # The actual next-page token — must be returned.
                        {
                            "continuationItemRenderer": {
                                "continuationEndpoint": {
                                    "continuationCommand": {
                                        "token": "NEXT_PAGE_TOKEN_4qmFsgI_comments",
                                        "request": "CONTINUATION_REQUEST_TYPE_WATCH_NEXT",
                                    }
                                }
                            }
                        },
                    ]
                }
            }
        ]
    }

    client = CommentAPIClient()
    try:
        result = client.extract_continuation_token(api_response)
    finally:
        client.close()

    assert result == "NEXT_PAGE_TOKEN_4qmFsgI_comments", (
        f"extracted {result!r} — likely picked up the nested reply token "
        f"instead of the top-level next-page token"
    )


def test_h3_extract_continuation_token_handles_appendContinuationItemsAction():
    """REGRESSION (H3): subsequent-page responses use
    appendContinuationItemsAction instead of
    reloadContinuationItemsCommand. The walker handles both.
    """
    from yt_meta.comment_api_client import CommentAPIClient

    api_response = {
        "onResponseReceivedEndpoints": [
            {
                "appendContinuationItemsAction": {
                    "continuationItems": [
                        {
                            "continuationItemRenderer": {
                                "continuationEndpoint": {
                                    "continuationCommand": {
                                        "token": "PAGE_3_TOKEN"
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        ]
    }
    client = CommentAPIClient()
    try:
        assert client.extract_continuation_token(api_response) == "PAGE_3_TOKEN"
    finally:
        client.close()


def test_h3_extract_continuation_token_returns_none_at_end_of_stream():
    """REGRESSION (H3): when no continuation token is present (end of
    comments), return None cleanly. Don't fall back to any token —
    that's what allowed the reply-token bug to ship.
    """
    from yt_meta.comment_api_client import CommentAPIClient

    api_response = {
        "onResponseReceivedEndpoints": [
            {
                "reloadContinuationItemsCommand": {
                    "continuationItems": [
                        # Only comment threads, no continuationItemRenderer
                        {"commentThreadRenderer": {"comment": {"text": "hi"}}},
                    ]
                }
            }
        ]
    }
    client = CommentAPIClient()
    try:
        assert client.extract_continuation_token(api_response) is None
    finally:
        client.close()


def test_h4_pagination_survives_one_all_duplicate_page(mocker):
    """REGRESSION (H4): CommentFetcher.get_comments did
    ``if not found_comments: break`` after processing each API page.
    If an entire page yielded no NEW comments (all ids in seen_ids —
    a legitimate case for sort_by='top' where YouTube can re-rank
    overlapping windows across continuation calls), the loop exited
    prematurely. Subsequent pages with new comments were never
    fetched. This also masked H3 (the reply-token DFS bug): when the
    wrong continuation token was extracted, the next page was all
    duplicates, this break fired, and the truncation was silent.

    Fix uses a consecutive-empty-page counter — break only after a
    threshold of consecutive pages with no new comments.
    """
    fetcher = CommentFetcher()
    mocker.patch.object(
        fetcher.api_client, "get_initial_video_data", return_value=({}, {})
    )
    mocker.patch.object(
        fetcher.api_client,
        "get_sort_endpoints_flexible",
        return_value={"recent": "endpoint"},
    )
    mocker.patch.object(
        fetcher.api_client, "select_sort_endpoint", return_value="tok1"
    )

    # 3 API pages: page 1 has c1 (new), page 2 has c1 again (dup), page 3 has c2 (new)
    mocker.patch.object(
        fetcher.api_client,
        "make_api_request",
        side_effect=[{"page": 1}, {"page": 2}, {"page": 3}, {"page": 4}],
    )
    mocker.patch.object(
        fetcher.api_client,
        "extract_continuation_token",
        side_effect=["tok2", "tok3", "tok4", None],
    )
    mocker.patch.object(
        fetcher.parser,
        "extract_complete_comments",
        side_effect=[
            [{"id": "c1", "text": "first"}],
            [{"id": "c1", "text": "first (dup)"}],
            [{"id": "c2", "text": "second"}],
            [{"id": "c2", "text": "second (dup)"}],
        ],
    )

    result = list(fetcher.get_comments("dQw4w9WgXcQ", sort_by="recent", limit=10))

    assert [c["id"] for c in result] == ["c1", "c2"], (
        "pagination broke on the first all-duplicate page; c2 was never fetched"
    )


def test_m19_get_comments_applies_filters_to_yielded_comments(mocker):
    """M19: CommentFetcher.get_comments accepts a `filters` dict and applies
    apply_comment_filters to each comment before yielding. Filters operate
    on the in-memory comment list (most comment filters cannot short-circuit
    pagination — that's only possible for since_date with sort_by='recent').
    """
    fetcher = CommentFetcher()
    mocker.patch.object(
        fetcher.api_client, "get_initial_video_data", return_value=({}, {})
    )
    mocker.patch.object(
        fetcher.api_client,
        "get_sort_endpoints_flexible",
        return_value={"recent": "endpoint"},
    )
    mocker.patch.object(
        fetcher.api_client, "select_sort_endpoint", return_value="cont_token"
    )
    mocker.patch.object(
        fetcher.api_client, "make_api_request", return_value={"some": "response"}
    )
    mocker.patch.object(
        fetcher.api_client, "extract_continuation_token", return_value=None
    )

    # R1 (2026-07-05): previously this test filtered synthetic dicts
    # hand-written in the filter layer's vocabulary — which is exactly
    # how the C1 phantom-key bug shipped. Now the REAL parser runs on a
    # REAL captured page: @jawed's own comment is the one is_creator
    # comment on it.
    import json
    from pathlib import Path

    with open(
        Path(__file__).parent / "fixtures" / "comment_first_page_pinned.json"
    ) as f:
        real_response = json.load(f)
    mocker.patch.object(
        fetcher.api_client, "make_api_request", return_value=real_response
    )

    filters = {"is_creator": {"eq": True}}
    result = list(
        fetcher.get_comments(
            "dQw4w9WgXcQ", sort_by="recent", limit=10, filters=filters
        )
    )

    assert [c["id"] for c in result] == ["Ugxnp9ws0dexjE9L5UB4AaABAg"]
    assert result[0]["is_creator"] is True


class TestBestCommentFetcher:
    """
    TDD tests for BestCommentFetcher
    These tests define the expected behavior before implementation
    """

    def setup_method(self):
        """Setup for each test"""
        self.fetcher = BestCommentFetcher()

    def test_init_creates_proper_client(self):
        """Test that initialization creates proper HTTP client"""
        fetcher = BestCommentFetcher(timeout=30, retries=5)
        assert fetcher.api_client is not None
        assert fetcher.api_client.retries == 5
        assert fetcher.parser is not None

    def test_get_comments_validates_since_date_with_sort_by(self):
        """Test that since_date only works with recent sorting"""
        with pytest.raises(
            ValueError, match="`since_date` can only be used with `sort_by='recent'`"
        ):
            list(
                self.fetcher.get_comments(
                    "dQw4w9WgXcQ", sort_by="top", since_date=date(2023, 1, 1)
                )
            )

    @patch("yt_meta.comment_api_client.httpx.Client")
    def test_get_comments_handles_video_unavailable(self, mock_client_class):
        """Test proper error handling for unavailable videos.

        M23 narrowed the outer ``except`` from ``Exception`` to httpx
        errors only, so this test must raise an httpx-level error to
        be wrapped as VideoUnavailableError. A plain Exception now
        surfaces unwrapped (as it should — that's the M23 fix).
        """
        import httpx

        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.side_effect = httpx.HTTPError("404 Not Found")

        fetcher = BestCommentFetcher()

        with pytest.raises(VideoUnavailableError):
            list(fetcher.get_comments("dQw4w9WgXcQ"))

    def test_comment_data_structure_completeness(self):
        """Test that returned comments have all expected fields with correct types"""
        expected_fields = {
            "id": str,
            "text": str,
            "author": str,
            "author_channel_id": str,
            "author_avatar_url": str,
            "publish_date": (date, type(None)),
            "time_human": str,
            "time_parsed": (float, type(None)),
            "like_count": int,
            "reply_count": int,
            "is_hearted": bool,
            "is_reply": bool,
            "is_pinned": bool,
            "paid_comment": (str, type(None)),
            "author_badges": list,
            "parent_id": (str, type(None)),
        }

        # Mock a complete comment response
        with (
            patch.object(self.fetcher.api_client, "make_api_request") as mock_request,
            patch.object(self.fetcher.api_client, "_extract_ytcfg") as mock_ytcfg,
            patch.object(self.fetcher.api_client, "_extract_initial_data") as mock_data,
            patch.object(
                self.fetcher.api_client, "get_sort_endpoints_flexible"
            ) as mock_endpoints,
        ):
            # Setup mocks
            mock_ytcfg.return_value = {
                "INNERTUBE_API_KEY": "test",
                "INNERTUBE_CONTEXT": {},
            }
            mock_data.return_value = {"test": "data"}
            mock_endpoints.return_value = {"top": "test_token"}
            mock_request.return_value = self._create_mock_comment_response()

            # Mock the HTTP client
            with patch.object(self.fetcher.api_client.client, "get") as mock_get:
                mock_response = Mock()
                mock_response.text = self._create_mock_html()
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response

                comments = list(self.fetcher.get_comments("dQw4w9WgXcQ", limit=1))

                assert len(comments) > 0
                comment = comments[0]

                # Check all expected fields exist and have correct types
                for field, expected_type in expected_fields.items():
                    assert field in comment, f"Missing field: {field}"
                    if isinstance(expected_type, tuple):
                        assert isinstance(comment[field], expected_type), (
                            f"Field {field} has wrong type: {type(comment[field])}, expected: {expected_type}"
                        )
                    else:
                        assert isinstance(comment[field], expected_type), (
                            f"Field {field} has wrong type: {type(comment[field])}, expected: {expected_type}"
                        )

    def test_engagement_count_parsing(self):
        """Test parsing of engagement counts like '1.2K', '58K', '325K'"""
        fetcher = BestCommentFetcher()

        # Test various count formats
        assert fetcher.parser._parse_engagement_count("120") == 120
        assert fetcher.parser._parse_engagement_count("1.2K") == 1200
        assert fetcher.parser._parse_engagement_count("58K") == 58000
        assert fetcher.parser._parse_engagement_count("325K") == 325000
        assert fetcher.parser._parse_engagement_count("1.5M") == 1500000
        assert fetcher.parser._parse_engagement_count("") == 0
        assert fetcher.parser._parse_engagement_count(None) == 0
        assert fetcher.parser._parse_engagement_count("invalid") == 0

    def test_flexible_endpoint_detection(self):
        """Test that endpoint detection works with different YouTube structures"""
        fetcher = BestCommentFetcher()

        # Test with sortFilterSubMenuRenderer present
        data_with_sort = {
            "nested": {
                "sortFilterSubMenuRenderer": {
                    "subMenuItems": [
                        {
                            "title": "Top comments",
                            "serviceEndpoint": {
                                "continuationCommand": {"token": "top_token"}
                            },
                        },
                        {
                            "title": "Newest first",
                            "serviceEndpoint": {
                                "continuationCommand": {"token": "recent_token"}
                            },
                        },
                    ]
                }
            }
        }

        endpoints = fetcher.api_client.get_sort_endpoints_flexible(
            data_with_sort, {"INNERTUBE_API_KEY": "test", "INNERTUBE_CONTEXT": {}}
        )
        assert "top comments" in endpoints
        assert "newest first" in endpoints
        assert endpoints["top comments"] == "top_token"
        assert endpoints["newest first"] == "recent_token"

    def test_surface_key_mapping(self):
        """Test surface key to comment ID mapping functionality"""
        fetcher = BestCommentFetcher()

        data = {
            "commentViewModel": [
                {"commentSurfaceKey": "surface_key_1", "commentId": "comment_id_1"},
                {"commentSurfaceKey": "surface_key_2", "commentId": "comment_id_2"},
            ]
        }

        surface_keys = fetcher.parser.get_surface_key_mappings(data)
        assert surface_keys["surface_key_1"] == "comment_id_1"
        assert surface_keys["surface_key_2"] == "comment_id_2"

    def test_toolbar_states_extraction(self):
        """Test toolbar states extraction for engagement data"""
        fetcher = BestCommentFetcher()

        data = {
            "mutations": [
                {
                    "payload": {
                        "engagementToolbarStateEntityPayload": {
                            "key": "toolbar_key_1",
                            "heartState": "TOOLBAR_HEART_STATE_HEARTED",
                        }
                    }
                },
                {
                    "payload": {
                        "engagementToolbarStateEntityPayload": {
                            "key": "toolbar_key_2",
                            "heartState": "TOOLBAR_HEART_STATE_UNHEARTED",
                        }
                    }
                },
            ]
        }

        toolbar_states = fetcher.parser.get_toolbar_states(data)
        assert "toolbar_key_1" in toolbar_states
        assert "toolbar_key_2" in toolbar_states
        assert (
            toolbar_states["toolbar_key_1"]["heartState"]
            == "TOOLBAR_HEART_STATE_HEARTED"
        )

    def test_paid_comments_extraction(self):
        """Test paid comment (Super Chat) detection"""
        fetcher = BestCommentFetcher()

        surface_keys = {"surface_key_1": "comment_id_1"}
        data = {
            "mutations": [
                {
                    "payload": {
                        "commentSurfaceEntityPayload": {
                            "key": "surface_key_1",
                            "pdgCommentChip": True,
                            "simpleText": "$5.00",
                        }
                    }
                }
            ]
        }

        paid_comments = fetcher.parser.get_paid_comments(data, surface_keys)
        assert "comment_id_1" in paid_comments
        assert paid_comments["comment_id_1"] == "$5.00"

    def test_progress_callback_called(self):
        """Test that progress callback is called during comment fetching"""
        callback_calls = []

        def progress_callback(count):
            callback_calls.append(count)

        # Mock the entire flow
        with (
            patch.object(self.fetcher.api_client, "make_api_request") as mock_request,
            patch.object(self.fetcher.api_client, "_extract_ytcfg") as mock_ytcfg,
            patch.object(self.fetcher.api_client, "_extract_initial_data") as mock_data,
            patch.object(
                self.fetcher.api_client, "get_sort_endpoints_flexible"
            ) as mock_endpoints,
        ):
            mock_ytcfg.return_value = {
                "INNERTUBE_API_KEY": "test",
                "INNERTUBE_CONTEXT": {},
            }
            mock_data.return_value = {"test": "data"}
            mock_endpoints.return_value = {"top": "test_token"}
            mock_request.return_value = self._create_mock_comment_response()

            with patch.object(self.fetcher.api_client.client, "get") as mock_get:
                mock_response = Mock()
                mock_response.text = self._create_mock_html()
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response

                list(
                    self.fetcher.get_comments(
                        "dQw4w9WgXcQ", limit=3, progress_callback=progress_callback
                    )
                )

                assert len(callback_calls) > 0
                assert callback_calls == [1, 2, 3]  # Should be called for each comment

    def test_limit_respected(self):
        """Test that the limit parameter is properly respected"""
        with (
            patch.object(self.fetcher.api_client, "make_api_request") as mock_request,
            patch.object(self.fetcher.api_client, "_extract_ytcfg") as mock_ytcfg,
            patch.object(self.fetcher.api_client, "_extract_initial_data") as mock_data,
            patch.object(
                self.fetcher.api_client, "get_sort_endpoints_flexible"
            ) as mock_endpoints,
        ):
            mock_ytcfg.return_value = {
                "INNERTUBE_API_KEY": "test",
                "INNERTUBE_CONTEXT": {},
            }
            mock_data.return_value = {"test": "data"}
            mock_endpoints.return_value = {"top": "test_token"}

            # Create response with multiple comments
            mock_request.return_value = self._create_mock_comment_response(
                num_comments=10
            )

            with patch.object(self.fetcher.api_client.client, "get") as mock_get:
                mock_response = Mock()
                mock_response.text = self._create_mock_html()
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response

                comments = list(self.fetcher.get_comments("dQw4w9WgXcQ", limit=3))

                assert len(comments) == 3

    def test_since_date_filtering(self):
        """Test that since_date filtering works correctly"""
        cutoff_date = date(2023, 1, 1)

        with (
            patch.object(self.fetcher.api_client, "make_api_request") as mock_request,
            patch.object(self.fetcher.api_client, "_extract_ytcfg") as mock_ytcfg,
            patch.object(self.fetcher.api_client, "_extract_initial_data") as mock_data,
            patch.object(
                self.fetcher.api_client, "get_sort_endpoints_flexible"
            ) as mock_endpoints,
        ):
            mock_ytcfg.return_value = {
                "INNERTUBE_API_KEY": "test",
                "INNERTUBE_CONTEXT": {},
            }
            mock_data.return_value = {"test": "data"}
            mock_endpoints.return_value = {"recent": "test_token"}

            # Create response with comments before and after cutoff
            mock_request.return_value = self._create_mock_comment_response_with_dates()

            with patch.object(self.fetcher.api_client.client, "get") as mock_get:
                mock_response = Mock()
                mock_response.text = self._create_mock_html()
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response

                comments = list(
                    self.fetcher.get_comments(
                        "dQw4w9WgXcQ", sort_by="recent", since_date=cutoff_date
                    )
                )

                # All returned comments should be after the cutoff date
                for comment in comments:
                    if comment["publish_date"]:
                        assert comment["publish_date"] >= cutoff_date

    def _create_mock_html(self):
        """Create mock HTML with required ytcfg and initial data"""
        return """
        <script>
        ytcfg.set({"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {"client": {"clientName": "WEB"}}});
        </script>
        <script>
        var ytInitialData = {"contents": {"test": "data"}};
        </script>
        """

    def _create_mock_comment_response(self, num_comments=3):
        """Create mock API response with comment data"""
        mutations = []

        # Create comment entity payloads
        for i in range(num_comments):
            mutations.append(
                {
                    "payload": {
                        "commentEntityPayload": {
                            "properties": {
                                "commentId": f"comment_id_{i}",
                                "content": {"content": f"Test comment {i}"},
                                "publishedTime": "2 years ago",
                                "toolbarStateKey": f"toolbar_key_{i}",
                                "authorKey": f"author_key_{i}",
                            }
                        }
                    }
                }
            )

        # Create author entity payloads
        for i in range(num_comments):
            mutations.append(
                {
                    "payload": {
                        "authorEntityPayload": {
                            "key": f"author_key_{i}",
                            "displayName": f"TestUser{i}",
                            "channelId": f"UC_channel_{i}",
                            "avatarThumbnailUrl": f"https://avatar{i}.jpg",
                        }
                    }
                }
            )

        # Create toolbar entity payloads
        for i in range(num_comments):
            mutations.append(
                {
                    "payload": {
                        "engagementToolbarEntityPayload": {
                            "key": f"toolbar_key_{i}",
                            "likeCountNotliked": str(100 + i),
                            "replyCount": str(i),
                        }
                    }
                }
            )

        return {
            "frameworkUpdates": {"entityBatchUpdate": {"mutations": mutations}},
            "commentViewModel": [
                {
                    "commentSurfaceKey": f"surface_key_{i}",
                    "commentId": f"comment_id_{i}",
                }
                for i in range(num_comments)
            ],
        }

    def _create_mock_comment_response_with_dates(self):
        """Create mock response with comments having different dates for filtering tests"""
        mutations = [
            # New comment
            {
                "payload": {
                    "commentEntityPayload": {
                        "properties": {
                            "commentId": "new_comment",
                            "content": {"content": "New comment"},
                            "publishedTime": "1 month ago",
                            "toolbarStateKey": "toolbar_key_new",
                            "authorKey": "author_key_new",
                        }
                    }
                }
            },
            {
                "payload": {
                    "authorEntityPayload": {
                        "key": "author_key_new",
                        "displayName": "NewUser",
                        "channelId": "UC_new",
                        "avatarThumbnailUrl": "https://avatar_new.jpg",
                    }
                }
            },
            {
                "payload": {
                    "engagementToolbarEntityPayload": {
                        "key": "toolbar_key_new",
                        "likeCountNotliked": "100",
                        "replyCount": "5",
                    }
                }
            },
            # Old comment
            {
                "payload": {
                    "commentEntityPayload": {
                        "properties": {
                            "commentId": "old_comment",
                            "content": {"content": "Old comment"},
                            "publishedTime": "3 years ago",
                            "toolbarStateKey": "toolbar_key_old",
                            "authorKey": "author_key_old",
                        }
                    }
                }
            },
            {
                "payload": {
                    "authorEntityPayload": {
                        "key": "author_key_old",
                        "displayName": "OldUser",
                        "channelId": "UC_old",
                        "avatarThumbnailUrl": "https://avatar_old.jpg",
                    }
                }
            },
            {
                "payload": {
                    "engagementToolbarEntityPayload": {
                        "key": "toolbar_key_old",
                        "likeCountNotliked": "50",
                        "replyCount": "2",
                    }
                }
            },
        ]

        return {
            "frameworkUpdates": {"entityBatchUpdate": {"mutations": mutations}},
            "commentViewModel": [
                {"commentSurfaceKey": "surface_key_new", "commentId": "new_comment"},
                {"commentSurfaceKey": "surface_key_old", "commentId": "old_comment"},
            ],
        }


def test_c4_limit_minus_one_is_unbounded_for_comments(
    mocker, comment_continuation_response
):
    """REGRESSION (C4, 2026-07-05 review): the docstring promises
    ``limit=-1`` (with since_date) means unbounded, but the loop guard
    ``comment_count < limit`` evaluated ``0 < -1`` → False, so no
    request was ever made and the generator was silently empty.
    R3: the documented special value gets its own test, on the real
    fixture through the real parser (R1)."""
    fetcher = CommentFetcher()
    mocker.patch.object(
        fetcher.api_client, "get_initial_video_data", return_value=({}, {})
    )
    mocker.patch.object(
        fetcher.api_client,
        "get_sort_endpoints_flexible",
        return_value={"newest first": "tok"},
    )
    mocker.patch.object(
        fetcher.api_client, "select_sort_endpoint", return_value="tok"
    )
    mocker.patch.object(
        fetcher.api_client,
        "make_api_request",
        return_value=comment_continuation_response,
    )
    mocker.patch.object(
        fetcher.api_client, "extract_continuation_token", return_value=None
    )

    comments = list(
        fetcher.get_comments("dQw4w9WgXcQ", limit=-1, since_date=date(2005, 1, 1))
    )
    # The real fixture page carries 20 comments; unbounded must yield all.
    assert len(comments) == 20


def test_c4_limit_minus_one_is_unbounded_for_replies(
    mocker, comment_continuation_response
):
    """REGRESSION (C4): same dead-loop guard in get_comment_replies."""
    fetcher = CommentFetcher()
    mocker.patch.object(
        fetcher.api_client, "get_initial_video_data", return_value=({}, {})
    )
    mocker.patch.object(
        fetcher.api_client,
        "make_reply_request",
        return_value=comment_continuation_response,
    )
    mocker.patch.object(
        fetcher.api_client, "extract_continuation_token", return_value=None
    )

    replies = list(
        fetcher.get_comment_replies("dQw4w9WgXcQ", "reply_tok", limit=-1)
    )
    assert len(replies) == 20


# --- C1 (2026-07-05 review): pinned/hearted wiring + working filter keys ---


@pytest.fixture(scope="module")
def first_page_pinned_response():
    """Real captured first page of 'Me at the zoo' (top sort): the
    pinned @jawed comment + 4 hearted comments, with the
    engagementToolbarStateEntityPayload ↔ toolbarStateKey linkage."""
    import json
    from pathlib import Path

    with open(
        Path(__file__).parent / "fixtures" / "comment_first_page_pinned.json"
    ) as f:
        return json.load(f)


def test_c1_is_pinned_wired_from_comment_view_model(first_page_pinned_response):
    """REGRESSION (C1): is_pinned was hardcoded False, making the
    documented pinned-comment workflow (example 28) a dead demo. The
    pinned state lives in commentViewModel.pinnedText, keyed by
    commentId."""
    from yt_meta.comment_parser import CommentParser

    comments = CommentParser().extract_complete_comments(first_page_pinned_response)
    pinned = [c for c in comments if c["is_pinned"]]
    assert [c["id"] for c in pinned] == ["UgzuC3zzpRZkjc5Qzsd4AaABAg"]
    # The pinnedText reads "Pinned by @jawed" — jawed pinned the
    # @SanDiegoZoo comment, so the AUTHOR is the zoo.
    assert pinned[0]["author"] == "@SanDiegoZoo"


def test_c1_is_hearted_wired_from_toolbar_state(first_page_pinned_response):
    """REGRESSION (C1): is_hearted was hardcoded False. The heart state
    lives in engagementToolbarStateEntityPayload.heartState, linked via
    properties.toolbarStateKey. The captured page has exactly 4 hearted
    comments."""
    from yt_meta.comment_parser import CommentParser

    comments = CommentParser().extract_complete_comments(first_page_pinned_response)
    hearted = {c["id"] for c in comments if c["is_hearted"]}
    assert hearted == {
        "UgzuC3zzpRZkjc5Qzsd4AaABAg",
        "Ugxnp9ws0dexjE9L5UB4AaABAg",
        "UgwVNlctFgmvFU1PTuN4AaABAg",
        "UgwzcjB8EtglNtvqSox4AaABAg",
    }


def test_c1_filters_work_on_real_parser_output(first_page_pinned_response):
    """REGRESSION (C1): filtering real parser output on the renamed
    keys (author_channel_id / is_hearted) must actually match. The old
    vocabulary (channel_id / is_hearted_by_owner / is_by_owner) never
    matched anything the parser emits — 100% of comments were dropped
    with no error."""
    from yt_meta.comment_parser import CommentParser
    from yt_meta.filtering import apply_comment_filters

    comments = CommentParser().extract_complete_comments(first_page_pinned_response)

    by_channel = [
        c
        for c in comments
        if apply_comment_filters(
            c, {"author_channel_id": {"eq": "UCC5NfQ6Mf0dq_eEwv4P_hWA"}}
        )
    ]
    assert by_channel, "author_channel_id filter must match the real comment"
    assert all(c["author"] == "@SanDiegoZoo" for c in by_channel)

    hearted = [
        c for c in comments if apply_comment_filters(c, {"is_hearted": {"eq": True}})
    ]
    assert len(hearted) == 4


def test_c1_old_filter_vocabulary_is_rejected_loudly():
    """REGRESSION (C1): the phantom keys must now fail fast at
    validate_filters (ValueError) instead of silently yielding zero
    comments."""
    from yt_meta.validators import validate_filters

    for key in ("channel_id", "is_by_owner", "is_hearted_by_owner"):
        with pytest.raises(ValueError, match="Unknown filter field"):
            validate_filters({key: {"eq": True}})


def test_c5_selective_filter_does_not_truncate_pagination(
    mocker, comment_continuation_response
):
    """REGRESSION (C5, 2026-07-05 review) / R6 interaction test
    (filters × pagination termination): found_comments counted
    post-filter survivors, so a rare filter (e.g. one specific author)
    tripped EMPTY_PAGE_LIMIT after 3 filtered-empty pages and silently
    missed matches deeper in the stream — contradicting the docstring
    ("filters do NOT reduce request count").

    Six pages derived from the real captured response (R9: ids
    re-suffixed per page so every page carries NEW comments; the target
    author is planted on pages 1 and 6). The fix counts new unique
    comment ids PRE-filter, so pagination must reach page 6.
    """
    import copy

    def make_page(page_num, plant_author=None):
        page = copy.deepcopy(comment_continuation_response)
        planted = False

        def rewrite(obj):
            nonlocal planted
            if isinstance(obj, dict):
                payload = obj.get("commentEntityPayload")
                if payload:
                    props = payload.get("properties", {})
                    if props.get("commentId"):
                        props["commentId"] = f"{props['commentId']}-p{page_num}"
                    if plant_author and not planted:
                        payload.setdefault("author", {})["displayName"] = plant_author
                        planted = True
                for v in obj.values():
                    rewrite(v)
            elif isinstance(obj, list):
                for v in obj:
                    rewrite(v)

        rewrite(page)
        return page

    target = "@the-needle-in-the-haystack"
    pages = [make_page(1, plant_author=target)] + [
        make_page(n) for n in range(2, 6)
    ] + [make_page(6, plant_author=target)]

    fetcher = CommentFetcher()
    mocker.patch.object(
        fetcher.api_client, "get_initial_video_data", return_value=({}, {})
    )
    mocker.patch.object(
        fetcher.api_client,
        "get_sort_endpoints_flexible",
        return_value={"newest first": "t1"},
    )
    mocker.patch.object(
        fetcher.api_client, "select_sort_endpoint", return_value="t1"
    )
    mocker.patch.object(fetcher.api_client, "make_api_request", side_effect=pages)
    mocker.patch.object(
        fetcher.api_client,
        "extract_continuation_token",
        side_effect=["t2", "t3", "t4", "t5", "t6", None],
    )

    result = list(
        fetcher.get_comments(
            "dQw4w9WgXcQ", filters={"author": {"eq": target}}
        )
    )
    assert len(result) == 2, (
        f"expected the planted matches from pages 1 AND 6, got "
        f"{len(result)} — pagination truncated by filtered-empty pages"
    )


def test_mc_extract_continuation_token_handles_button_form():
    """REGRESSION (M-c, 2026-07-05 review): reply-thread "Show more
    replies" pages carry the next-page token in the BUTTON form —
    continuationItemRenderer.button.buttonRenderer.command
    .continuationCommand.token — not the continuationEndpoint form the
    H3 rewrite handled. extract_continuation_token returned None, so
    get_comment_replies silently stopped after ~10 replies.

    Fixture: REAL reply continuation page captured live from the pinned
    'Me at the zoo' thread (hundreds of replies). Note the same page
    also contains button-form continuation renderers NESTED inside
    commentRepliesRenderer.subThreads — the H3 discipline (top-level
    continuationItems only, reversed scan) must keep excluding those.
    """
    import json
    from pathlib import Path

    from yt_meta.comment_api_client import CommentAPIClient

    with open(
        Path(__file__).parent
        / "fixtures"
        / "comment_reply_page_with_continuation.json"
    ) as f:
        reply_response = json.load(f)

    client = CommentAPIClient()
    try:
        token = client.extract_continuation_token(reply_response)
    finally:
        client.close()
    assert token, "button-form next-page token was not extracted"
    # the real token from the captured page
    assert token.startswith("Eg0SC2pOUVhBQzlJVlJ3")
    # H3 safety: the nested subThreads tokens must NOT be returned.
    # (The top-level item is the LAST continuationItemRenderer; nested
    # ones live inside commentThreadRenderer subtrees we never enter.)


# --- M-d (2026-07-05 review): remaining broad excepts must not swallow bugs ---


def _fetcher_with_pages(mocker, pages):
    """CommentFetcher with the api boundary scripted; parser runs real."""
    fetcher = CommentFetcher()
    mocker.patch.object(
        fetcher.api_client, "get_initial_video_data", return_value=({}, {})
    )
    mocker.patch.object(
        fetcher.api_client,
        "get_sort_endpoints_flexible",
        return_value={"newest first": "t1"},
    )
    mocker.patch.object(fetcher.api_client, "select_sort_endpoint", return_value="t1")
    mocker.patch.object(fetcher.api_client, "make_api_request", side_effect=pages)
    return fetcher


def test_md_parser_bug_mid_pagination_propagates(mocker, comment_continuation_response):
    """REGRESSION (M-d): the inner `except Exception: log + break` in the
    get_comments loop converted any parser bug (KeyError from a YouTube
    shape change) into a silently truncated — but complete-looking —
    comment stream. Programmer errors must surface."""
    fetcher = _fetcher_with_pages(mocker, [comment_continuation_response])
    mocker.patch.object(
        fetcher.parser,
        "extract_complete_comments",
        side_effect=KeyError("shape changed"),
    )
    with pytest.raises(KeyError):
        list(fetcher.get_comments("dQw4w9WgXcQ"))


def test_md_http_failure_mid_pagination_raises_video_unavailable(
    mocker, monkeypatch
):
    """REGRESSION (M-d): make_api_request swallowed every exception to
    None, so a persistent HTTP failure mid-pagination silently truncated
    the stream. It must surface as VideoUnavailableError (the documented
    HTTP-failure contract). R1: the 500s are real responses through
    httpx.MockTransport; the real retry path runs (sleep patched)."""
    import httpx

    monkeypatch.setattr("yt_meta._retry.time.sleep", lambda _s: None)
    session = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(500))
    )
    try:
        fetcher = CommentFetcher(session=session)
        mocker.patch.object(
            fetcher.api_client,
            "get_initial_video_data",
            return_value=({}, {"INNERTUBE_API_KEY": "k", "INNERTUBE_CONTEXT": {}}),
        )
        mocker.patch.object(
            fetcher.api_client,
            "get_sort_endpoints_flexible",
            return_value={"newest first": "t1"},
        )
        mocker.patch.object(
            fetcher.api_client, "select_sort_endpoint", return_value="t1"
        )
        with pytest.raises(VideoUnavailableError):
            list(fetcher.get_comments("dQw4w9WgXcQ"))
    finally:
        session.close()


def test_md_reply_parser_bug_propagates(mocker, comment_continuation_response):
    """REGRESSION (M-d): same inner-swallow in get_comment_replies, plus
    its OUTER handler still wrapped bare Exception as
    VideoUnavailableError — misreporting programmer bugs as 'video
    unavailable' (the M23 fix was applied only to get_comments)."""
    fetcher = CommentFetcher()
    mocker.patch.object(
        fetcher.api_client, "get_initial_video_data", return_value=({}, {})
    )
    mocker.patch.object(
        fetcher.api_client,
        "make_reply_request",
        return_value=comment_continuation_response,
    )
    mocker.patch.object(
        fetcher.parser,
        "extract_complete_comments",
        side_effect=KeyError("shape changed"),
    )
    with pytest.raises(KeyError):
        list(fetcher.get_comment_replies("dQw4w9WgXcQ", "tok"))
