"""Offline coverage for the comment subsystem.

The comment subsystem (``comment_api_client`` / ``comment_fetcher`` /
``comment_parser``) was the weakest-covered code in the library (55-58%),
and — per the ultra-review — its most fragile: the continuation-token
extractor (H3) and the pagination-break logic (H4) are exactly where a
silent truncation hides. These tests exercise that logic offline with
synthetic payloads and mocks (no network), plus the real captured
fixtures where a real-shape payload matters.
"""

from datetime import date
from unittest.mock import Mock

import httpx
import pytest

from yt_meta.comment_api_client import CommentAPIClient
from yt_meta.comment_fetcher import CommentFetcher
from yt_meta.comment_parser import CommentParser
from yt_meta.exceptions import VideoUnavailableError

# ---------------------------------------------------------------------------
# CommentParser._parse_engagement_count — the "1.2K"/"58K"/"3.4M" formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (42, 42),  # int passthrough
        ("325", 325),  # plain digits
        ("1.2K", 1200),  # decimal thousands
        ("58K", 58000),  # integer thousands
        ("3.4M", 3400000),  # decimal millions
        ("2M", 2000000),  # integer millions
        ("1.5B", 1500000000),  # decimal billions
        ("2B", 2000000000),  # integer billions
        ("12.0", 12),  # float-as-string
        ("", 0),  # empty
        (None, 0),  # None
        ("garbage", 0),  # unparseable -> 0, not a crash
        ([], 0),  # wrong type -> 0
    ],
)
def test_parse_engagement_count(value, expected):
    assert CommentParser()._parse_engagement_count(value) == expected


# ---------------------------------------------------------------------------
# CommentParser.parse_comment_complete — the legacy per-comment parser
# (lines 302-401: avatar variants, badges, hearted, paid, pinned, reply)
# ---------------------------------------------------------------------------


def test_parse_comment_complete_full_metadata():
    parser = CommentParser()
    comment_data = {
        "commentId": "c1",
        "content": {"content": "hello world"},
        "authorKey": "ak1",
        "toolbarStateKey": "tk1",
        "publishedTimeText": "2 days ago",
        "pinnedText": "Pinned by creator",
    }
    author_payloads = {
        "ak1": {
            "displayName": "Alice",
            "channelId": "UC_alice",
            "avatar": {"thumbnails": [{"url": "small.jpg"}, {"url": "big.jpg"}]},
            "authorBadges": [{"type": "VERIFIED"}, {"type": "MEMBER"}, "not-a-dict"],
        }
    }
    toolbar_payloads = {"tk1": {"likeCountNotliked": "1.2K", "replyCount": "5"}}
    toolbar_states = {"tk1": {"heartState": "TOOLBAR_HEART_STATE_HEARTED"}}
    paid_comments = {"c1": "$5.00"}

    result = parser.parse_comment_complete(
        comment_data,
        author_payloads,
        toolbar_payloads,
        toolbar_states,
        paid_comments,
        surface_keys={},
    )

    assert result["id"] == "c1"
    assert result["text"] == "hello world"
    assert result["author"] == "Alice"
    assert result["author_channel_id"] == "UC_alice"
    # highest-resolution thumbnail (last) is preferred
    assert result["author_avatar_url"] == "big.jpg"
    assert result["author_badges"] == ["VERIFIED", "MEMBER"]
    assert result["like_count"] == 1200
    assert result["reply_count"] == 5
    assert result["is_hearted"] is True
    assert result["is_pinned"] is True
    assert result["paid_comment"] == "$5.00"
    assert result["is_reply"] is False
    assert result["parent_id"] is None


def test_parse_comment_complete_direct_avatar_and_reply():
    parser = CommentParser()
    comment_data = {
        "commentId": "r1",
        "content": {"content": "a reply"},
        "authorKey": "ak2",
        "parentCommentKey": "c1",  # makes it a reply
    }
    author_payloads = {"ak2": {"displayName": "Bob", "avatarThumbnailUrl": "bob.jpg"}}

    result = parser.parse_comment_complete(
        comment_data, author_payloads, {}, {}, {}, {}
    )

    assert result["author_avatar_url"] == "bob.jpg"  # direct-url branch
    assert result["is_reply"] is True
    assert result["parent_id"] == "c1"
    assert result["is_hearted"] is False
    assert result["is_pinned"] is False


def test_parse_comment_complete_returns_none_without_id():
    parser = CommentParser()
    assert parser.parse_comment_complete({}, {}, {}, {}, {}, {}) is None


def test_parse_comment_complete_swallows_bad_data():
    """The broad try/except returns None instead of crashing the whole
    fetch when a single comment's shape is unexpected."""
    parser = CommentParser()
    # content is a string, not a dict -> .get() inside raises -> None
    bad = {"commentId": "c1", "content": "not-a-dict"}
    assert parser.parse_comment_complete(bad, {}, {}, {}, {}, {}) is None


# ---------------------------------------------------------------------------
# CommentParser search helpers — driven with small synthetic payloads
# ---------------------------------------------------------------------------


def test_extract_comment_and_author_and_toolbar_payloads():
    parser = CommentParser()
    api = {
        "frameworkUpdates": {
            "entityBatchUpdate": {
                "mutations": [
                    {
                        "payload": {
                            "commentEntityPayload": {
                                "key": "k1",
                                "properties": {"commentId": "c1"},
                                "author": {"displayName": "Alice"},
                            }
                        }
                    },
                    {
                        "payload": {
                            "engagementToolbarSurfaceEntityPayload": {
                                "key": "t1",
                                "likeCountNotliked": "5",
                            }
                        }
                    },
                    {
                        "payload": {
                            "engagementToolbarStateEntityPayload": {
                                "key": "t1",
                                "heartState": "HEARTED",
                            }
                        }
                    },
                ]
            }
        }
    }

    payloads = parser.extract_comment_payloads(api)
    assert payloads == [{"commentId": "c1"}]

    authors = parser.extract_author_payloads(api)
    assert authors == {"k1": {"displayName": "Alice"}}

    # surface + state payloads with the same key are merged
    toolbars = parser.extract_toolbar_payloads(api)
    assert toolbars["t1"]["likeCountNotliked"] == "5"
    assert toolbars["t1"]["heartState"] == "HEARTED"

    states = parser.get_toolbar_states(api)
    assert states["t1"]["heartState"] == "HEARTED"


def test_get_surface_key_mappings_and_paid_comments():
    parser = CommentParser()
    api = {
        "x": {"commentSurfaceKey": "sk1", "commentId": "c1"},
        "y": {
            "commentSurfaceEntityPayload": {
                "key": "sk1",
                "pdgCommentChip": {"a": 1},
                "simpleText": "$10.00",
            }
        },
    }
    surface_keys = parser.get_surface_key_mappings(api)
    assert surface_keys == {"sk1": "c1"}

    paid = parser.get_paid_comments(api, surface_keys)
    assert paid == {"c1": "$10.00"}


# ---------------------------------------------------------------------------
# CommentAPIClient.extract_continuation_token — the H3 regression
# ---------------------------------------------------------------------------


def _next_page_renderer(token):
    return {
        "continuationItemRenderer": {
            "continuationEndpoint": {"continuationCommand": {"token": token}}
        }
    }


def test_extract_continuation_token_ignores_reply_tokens_h3():
    """REGRESSION (H3): the extractor must return the bottom-of-page
    next-comments token, NOT a reply continuation token embedded inside a
    per-thread renderer. The old DFS returned the first token matching a
    fuzzy 'replies' substring check, which lived inside the thread and was
    reached first — silently truncating the comment stream.
    """
    api_response = {
        "onResponseReceivedEndpoints": [
            {
                "reloadContinuationItemsCommand": {
                    "continuationItems": [
                        # A comment thread that itself carries a NESTED reply
                        # continuation token (the H3 trap).
                        {
                            "commentThreadRenderer": {
                                "replies": {
                                    "commentRepliesRenderer": {
                                        "contents": [
                                            {
                                                "continuationItemRenderer": {
                                                    "continuationEndpoint": {
                                                        "continuationCommand": {
                                                            "token": "REPLY_TOKEN"
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                        # The real next-page token at the bottom of the page.
                        _next_page_renderer("NEXT_PAGE_TOKEN"),
                    ]
                }
            }
        ]
    }
    token = CommentAPIClient().extract_continuation_token(api_response)
    assert token == "NEXT_PAGE_TOKEN"


def test_extract_continuation_token_append_variant():
    api_response = {
        "onResponseReceivedEndpoints": [
            {
                "appendContinuationItemsAction": {
                    "continuationItems": [_next_page_renderer("PAGE2")]
                }
            }
        ]
    }
    assert CommentAPIClient().extract_continuation_token(api_response) == "PAGE2"


def test_extract_continuation_token_none_at_end_of_stream():
    # A page of only comment threads (no trailing continuationItemRenderer)
    # means the stream is exhausted.
    api_response = {
        "onResponseReceivedEndpoints": [
            {
                "reloadContinuationItemsCommand": {
                    "continuationItems": [{"commentThreadRenderer": {}}]
                }
            }
        ]
    }
    assert CommentAPIClient().extract_continuation_token(api_response) is None


@pytest.mark.parametrize("bad", [None, "string", 42, []])
def test_extract_continuation_token_non_dict(bad):
    assert CommentAPIClient().extract_continuation_token(bad) is None


# ---------------------------------------------------------------------------
# CommentAPIClient token / endpoint helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token, expected",
    [
        ("xxxxxxcommentsxxxxxx", True),  # contains 'comments'
        ("token_with_replies_in_it", True),  # contains 'replies'
        ("a_discussion_token_here", True),  # contains 'discussion'
        ("short", False),  # too short (< 10 chars)
        (12345, False),  # not a string
        ("randomtokenwithoutindicators", False),
    ],
)
def test_is_comment_token(token, expected):
    assert CommentAPIClient()._is_comment_token(token) is expected


def test_is_comment_token_prefix_indicator_is_case_sensitive():
    """KNOWN QUIRK: ``_is_comment_token`` lowercases the token before
    matching, but the ``"4qmFsgI"`` indicator is mixed-case, so a bare
    canonical-prefix token is NOT recognized by that indicator alone.
    Documented here so a future "fix" to the indicator doesn't silently
    change fallback endpoint detection without a failing test. (Real
    comment tokens still match via the 'comments'/'replies' substrings.)
    """
    assert CommentAPIClient()._is_comment_token("4qmFsgIabc1234567890") is False


@pytest.mark.parametrize(
    "sort_by, expected",
    [
        ("top", "TOP_TOKEN"),
        ("recent", "RECENT_TOKEN"),
    ],
)
def test_select_sort_endpoint_prefers_correct(sort_by, expected):
    endpoints = {"top comments": "TOP_TOKEN", "newest first": "RECENT_TOKEN"}
    assert CommentAPIClient().select_sort_endpoint(endpoints, sort_by) == expected


def test_select_sort_endpoint_fallback_and_empty():
    client = CommentAPIClient()
    # No preference match -> fall back to the first available endpoint.
    assert client.select_sort_endpoint({"weird key": "TOK"}, "top") == "TOK"
    # No endpoints at all -> None.
    assert client.select_sort_endpoint({}, "top") is None


def test_get_sort_endpoints_flexible_from_submenu():
    initial_data = {
        "sortFilterSubMenuRenderer": {
            "subMenuItems": [
                {
                    "title": "Top comments",
                    "serviceEndpoint": {"continuationCommand": {"token": "TOPTOK"}},
                },
                {
                    "title": "Newest first",
                    "serviceEndpoint": {"continuationCommand": {"token": "NEWTOK"}},
                },
            ]
        }
    }
    endpoints = CommentAPIClient().get_sort_endpoints_flexible(initial_data, {})
    assert endpoints == {"top comments": "TOPTOK", "newest first": "NEWTOK"}


def test_get_sort_endpoints_flexible_engagement_panel_fallback():
    """When no sortFilterSubMenuRenderer exists, fall back to scanning
    engagement panels for comment continuation tokens."""
    initial_data = {
        "engagementPanels": [
            {
                "engagementPanelSectionListRenderer": {
                    "panelIdentifier": "comment-item-section",
                    "header": {"title": "Comments"},
                    "continuationItemRenderer": {
                        "continuationEndpoint": {
                            "continuationCommand": {"token": "4qmFsgItopcomments"}
                        }
                    },
                }
            }
        ]
    }
    endpoints = CommentAPIClient().get_sort_endpoints_flexible(initial_data, {})
    assert "4qmFsgItopcomments" in endpoints.values()


# ---------------------------------------------------------------------------
# CommentAPIClient HTTP request helpers (mocked client, no network)
# ---------------------------------------------------------------------------


def _client_with_post(post_return=None, post_side_effect=None):
    session = Mock(spec=httpx.Client)
    if post_side_effect is not None:
        session.post.side_effect = post_side_effect
    else:
        resp = Mock()
        resp.status_code = 200
        resp.raise_for_status = Mock()
        resp.json.return_value = post_return
        session.post.return_value = resp
    return CommentAPIClient(session=session)


def test_make_api_request_no_api_key_returns_none():
    assert _client_with_post().make_api_request("tok", ytcfg={}) is None


def test_make_api_request_success():
    client = _client_with_post(post_return={"ok": True})
    out = client.make_api_request("tok", ytcfg={"INNERTUBE_API_KEY": "k"})
    assert out == {"ok": True}


def test_make_api_request_propagates_errors():
    """M-d (0.8.0): make_api_request no longer swallows exceptions to
    None — None looked like a normal end-of-stream to the pagination
    loop, silently truncating results on persistent failures."""
    client = _client_with_post(post_side_effect=ValueError("boom"))
    with pytest.raises(ValueError):
        client.make_api_request("tok", ytcfg={"INNERTUBE_API_KEY": "k"})


def test_make_reply_request_paths():
    assert _client_with_post().make_reply_request("tok", {}) is None
    ok = _client_with_post(post_return={"r": 1}).make_reply_request(
        "tok", {"INNERTUBE_API_KEY": "k"}
    )
    assert ok == {"r": 1}


def test_extract_ytcfg_and_initial_data():
    client = CommentAPIClient()
    html_ok = (
        'foo ytcfg.set({"INNERTUBE_API_KEY": "abc"}); var ytInitialData = {"a": 1};'
    )
    assert client._extract_ytcfg(html_ok) == {"INNERTUBE_API_KEY": "abc"}
    assert client._extract_initial_data(html_ok) == {"a": 1}
    # Malformed JSON -> empty dict, not a crash.
    assert client._extract_ytcfg("ytcfg.set({not json});") == {}
    assert client._extract_initial_data("var ytInitialData = {nope};") == {}


# ---------------------------------------------------------------------------
# CommentFetcher orchestration (mocked api_client + parser, no network)
# ---------------------------------------------------------------------------


def _fetcher_with_mocks():
    fetcher = CommentFetcher()
    fetcher.api_client = Mock()
    fetcher.parser = Mock()
    fetcher.api_client.get_initial_video_data.return_value = ({}, {"k": "v"})
    fetcher.parser.extract_reply_continuations.return_value = {}
    return fetcher


def test_get_comments_since_date_requires_recent():
    with pytest.raises(ValueError):
        list(
            CommentFetcher().get_comments(
                "dQw4w9WgXcQ", sort_by="top", since_date=date(2024, 1, 1)
            )
        )


def test_get_comments_no_endpoints_yields_nothing():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_sort_endpoints_flexible.return_value = {}
    assert list(fetcher.get_comments("dQw4w9WgXcQ")) == []


def test_get_comments_no_token_yields_nothing():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_sort_endpoints_flexible.return_value = {"newest first": "t"}
    fetcher.api_client.select_sort_endpoint.return_value = None
    assert list(fetcher.get_comments("dQw4w9WgXcQ")) == []


def test_get_comments_happy_path_dedupes_and_stops():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_sort_endpoints_flexible.return_value = {"newest first": "t0"}
    fetcher.api_client.select_sort_endpoint.return_value = "t0"
    fetcher.api_client.make_api_request.return_value = {"page": 1}
    # Page returns c1, c2, then a duplicate c1 (dedup), then no more pages.
    fetcher.parser.extract_complete_comments.return_value = [
        {"id": "c1", "text": "one"},
        {"id": "c2", "text": "two"},
        {"id": "c1", "text": "dup"},
    ]
    fetcher.api_client.extract_continuation_token.return_value = None

    out = list(fetcher.get_comments("dQw4w9WgXcQ"))
    assert [c["id"] for c in out] == ["c1", "c2"]


def test_get_comments_since_date_filters_old():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_sort_endpoints_flexible.return_value = {"newest first": "t0"}
    fetcher.api_client.select_sort_endpoint.return_value = "t0"
    fetcher.api_client.make_api_request.return_value = {"page": 1}
    fetcher.parser.extract_complete_comments.return_value = [
        {"id": "new", "publish_date": date(2024, 6, 1)},
        {"id": "old", "publish_date": date(2020, 1, 1)},
    ]
    fetcher.api_client.extract_continuation_token.return_value = None

    out = list(fetcher.get_comments("dQw4w9WgXcQ", since_date=date(2024, 1, 1)))
    assert [c["id"] for c in out] == ["new"]


def test_get_comments_breaks_after_consecutive_empty_pages_h4():
    """REGRESSION (H4): an all-duplicate page must NOT immediately
    truncate the stream — the fetcher tolerates EMPTY_PAGE_LIMIT-1
    consecutive empty pages before giving up. Here every page after the
    first is all-duplicate; the loop must stop (not spin forever) and
    return only the unique comments seen.
    """
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_sort_endpoints_flexible.return_value = {"newest first": "t0"}
    fetcher.api_client.select_sort_endpoint.return_value = "t0"
    fetcher.api_client.make_api_request.return_value = {"page": "x"}
    # Always the same single comment -> first page yields it, every later
    # page is all-duplicate.
    fetcher.parser.extract_complete_comments.return_value = [{"id": "c1"}]
    # Token never advances to None on its own; the empty-page counter must
    # be what terminates the loop.
    fetcher.api_client.extract_continuation_token.return_value = "same-token"

    out = list(fetcher.get_comments("dQw4w9WgXcQ"))
    assert [c["id"] for c in out] == ["c1"]
    # First page (1 new) + EMPTY_PAGE_LIMIT all-duplicate pages = 4 calls.
    assert fetcher.api_client.make_api_request.call_count == 4


def test_get_comments_attaches_reply_continuation_token():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_sort_endpoints_flexible.return_value = {"newest first": "t0"}
    fetcher.api_client.select_sort_endpoint.return_value = "t0"
    fetcher.api_client.make_api_request.return_value = {"page": 1}
    fetcher.parser.extract_complete_comments.return_value = [{"id": "c1"}]
    fetcher.parser.extract_reply_continuations.return_value = {"c1": "REPLYTOK"}
    fetcher.api_client.extract_continuation_token.return_value = None

    out = list(fetcher.get_comments("dQw4w9WgXcQ", include_reply_continuation=True))
    assert out[0]["reply_continuation_token"] == "REPLYTOK"


def test_get_comments_wraps_http_error_as_unavailable():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_sort_endpoints_flexible.side_effect = httpx.HTTPError("nope")
    with pytest.raises(VideoUnavailableError):
        list(fetcher.get_comments("dQw4w9WgXcQ"))


# ---------------------------------------------------------------------------
# CommentFetcher.get_comment_replies (the big uncovered block, 243-308)
# ---------------------------------------------------------------------------


def test_get_comment_replies_happy_path_marks_replies():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.make_reply_request.return_value = {"page": 1}
    fetcher.parser.extract_complete_comments.return_value = [
        {"id": "r1", "is_reply": False, "reply_count": 9, "is_pinned": True},
        {"id": "r2", "is_reply": False, "reply_count": 9, "is_pinned": True},
    ]
    fetcher.api_client.extract_continuation_token.return_value = None

    out = list(fetcher.get_comment_replies("dQw4w9WgXcQ", "REPLYTOK"))
    assert [r["id"] for r in out] == ["r1", "r2"]
    # Reply-specific normalization is applied.
    assert all(r["is_reply"] is True for r in out)
    assert all(r["reply_count"] == 0 for r in out)
    assert all(r["is_pinned"] is False for r in out)


def test_get_comment_replies_breaks_when_no_new_replies():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.make_reply_request.return_value = {"page": 1}
    # Same reply id every page -> after the first, no new replies -> break.
    fetcher.parser.extract_complete_comments.return_value = [{"id": "r1"}]
    fetcher.api_client.extract_continuation_token.return_value = "again"

    out = list(fetcher.get_comment_replies("dQw4w9WgXcQ", "REPLYTOK"))
    assert [r["id"] for r in out] == ["r1"]
    assert fetcher.api_client.make_reply_request.call_count == 2


def test_get_comment_replies_respects_limit():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.make_reply_request.return_value = {"page": 1}
    fetcher.parser.extract_complete_comments.return_value = [
        {"id": "r1"},
        {"id": "r2"},
        {"id": "r3"},
    ]
    fetcher.api_client.extract_continuation_token.return_value = None

    out = list(fetcher.get_comment_replies("dQw4w9WgXcQ", "REPLYTOK", limit=2))
    assert [r["id"] for r in out] == ["r1", "r2"]


def test_get_comment_replies_stops_on_empty_response():
    fetcher = _fetcher_with_mocks()
    fetcher.api_client.make_reply_request.return_value = None
    assert list(fetcher.get_comment_replies("dQw4w9WgXcQ", "REPLYTOK")) == []


def test_get_comment_replies_wraps_http_errors_propagates_bugs():
    """M-d (0.8.0): only genuine HTTP failures are wrapped as
    VideoUnavailableError; programmer bugs propagate unwrapped (the
    M23 contract, previously applied only to get_comments)."""
    import httpx

    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_initial_video_data.side_effect = httpx.ConnectError("net down")
    with pytest.raises(VideoUnavailableError):
        list(fetcher.get_comment_replies("dQw4w9WgXcQ", "REPLYTOK"))

    fetcher = _fetcher_with_mocks()
    fetcher.api_client.get_initial_video_data.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        list(fetcher.get_comment_replies("dQw4w9WgXcQ", "REPLYTOK"))


# ---------------------------------------------------------------------------
# Real-fixture coverage for the reply-token extractor
# ---------------------------------------------------------------------------


def test_extract_reply_continuations_subthreads_fixture():
    """The subThreads-shape fixture (current YouTube shape) must yield a
    reply token — guards the e92cfd0 subThreads migration fix."""
    import json
    from pathlib import Path

    data = json.loads(
        (
            Path(__file__).parent / "fixtures" / "comment_threads_subthreads.json"
        ).read_text()
    )
    tokens = CommentParser().extract_reply_continuations(data)
    assert tokens, "no reply tokens extracted from subThreads fixture"
    assert all(isinstance(t, str) and t for t in tokens.values())
