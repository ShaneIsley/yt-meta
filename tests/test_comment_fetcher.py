import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from yt_meta.comment_fetcher import CommentFetcher
from yt_meta.exceptions import VideoUnavailableError

FIXTURES_PATH = Path(__file__).parent / "fixtures"

@pytest.fixture
def fetcher():
    return CommentFetcher()

@pytest.fixture
def video_page_html():
    with open(FIXTURES_PATH / "B68agR-OeJM.html", encoding="utf-8") as f:
        return f.read()

@pytest.fixture
def initial_comment_data():
    with open(FIXTURES_PATH / "aimakerspace_channel_initial_data.json", encoding="utf-8") as f:
        return json.load(f)

@pytest.fixture
def continuation_json():
    with open(FIXTURES_PATH / "comment_continuation_response.json", encoding="utf-8") as f:
        return json.load(f)

@pytest.fixture
def reply_json():
    with open(FIXTURES_PATH / "comment_reply_response.json", encoding="utf-8") as f:
        return json.load(f)

def test_parse_initial_comments(fetcher, initial_comment_data, mocker):
    """ Test parser handles initial comment data structure. """
    mocker.patch.object(fetcher, '_find_comment_page_continuation', return_value=None)
    mocker.patch.object(fetcher, '_parse_comments', return_value=[{"text": "hello", "author": "test", "like_count": 1}])
    mocker.patch.object(fetcher, '_extract_initial_data', return_value=initial_comment_data)
    mocker.patch.object(fetcher._client, 'get', return_value=mocker.Mock(status_code=200, text='ytcfg.set({"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {"client": {"clientName": "WEB", "clientVersion": "2.20210721.00.00"}}});'))

    comments = list(fetcher.get_comments("any_id", limit=1))

    assert len(comments) > 0
    assert "like_count" in comments[0]
    assert comments[0]["author"] is not None

def test_parse_continuation_comments(fetcher, continuation_json, mocker):
    """ Test parser handles continuation data structure. """
    mocker.patch.object(fetcher, '_find_comment_page_continuation', return_value=None)
    mocker.patch.object(fetcher, '_parse_comments', return_value=[{"text": "hello", "author": "test", "like_count": 1}])
    mocker.patch.object(fetcher, '_extract_initial_data', return_value={"contents": {"twoColumnWatchNextResults": {"results": {"results": {"contents": [{"itemSectionRenderer": {"contents": [{"continuationItemRenderer": {"continuationEndpoint": {"commentActionButtonsRenderer": {"sortMenu": {"sortFilterSubMenuRenderer": {"subMenuItems": [{"title": "Top comments", "serviceEndpoint": {"continuationCommand": {"token": "fake_token"}}}]}}}}}}]}}]}}}}})
    mocker.patch.object(fetcher, '_get_sort_endpoints', return_value={"top": ("fake_token", None, None)})
    mocker.patch.object(fetcher, '_find_api_key_and_context', return_value=("key", "context"))
    mocker.patch.object(fetcher._client, 'post', return_value=mocker.Mock(status_code=200, json=lambda: continuation_json))
    mocker.patch.object(fetcher._client, 'get', return_value=mocker.Mock(status_code=200, text=""))

    comments = list(fetcher.get_comments("any_id", limit=1))

    assert len(comments) > 0
    assert "like_count" in comments[0]
    assert comments[0]["author"] is not None

def test_get_comments_end_to_end(fetcher, video_page_html, initial_comment_data, continuation_json, mocker):
    """ Verify get_comments successfully fetches and parses from a mocked flow. """

    # Mock the initial HTTP GET to return the video page HTML
    mock_get = mocker.patch.object(fetcher._client, 'get', return_value=mocker.Mock(
        status_code=200, text=video_page_html,
    ))
    mock_get.return_value.raise_for_status = mocker.Mock()

    # Mock the extraction of initial data from the HTML
    mocker.patch.object(fetcher, '_extract_initial_data', return_value=initial_comment_data)
    mocker.patch.object(fetcher, '_parse_comments', side_effect=[[{"text": "a"}] * 20, [{"text": "b"}] * 20])

    # Mock the subsequent HTTP POST for continuation
    mock_post = mocker.patch.object(fetcher._client, 'post', return_value=mocker.Mock(
        status_code=200, json=lambda: continuation_json,
    ))
    mock_post.return_value.raise_for_status = mocker.Mock()
    mocker.patch.object(fetcher, '_get_sort_endpoints', return_value={"top": ("fake_token", None, None)})
    mocker.patch.object(fetcher, '_find_api_key_and_context', return_value=("key", "context"))

    # Mock the continuation token finder to stop after one page of continued comments
    mocker.patch.object(fetcher, '_find_comment_page_continuation', side_effect=["fake_continuation_token", None])

    # Run the full flow
    comments = list(fetcher.get_comments("B68agR-OeJM", limit=40))

    # Assertions
    # We expect comments from both the initial data and the continuation data
    assert len(comments) > 20
    assert "text" in comments[0]
    assert "text" in comments[-1]

    # Verify the initial GET was called
    mock_get.assert_called_once_with("https://www.youtube.com/watch?v=B68agR-OeJM", follow_redirects=True)

    # Verify that a POST was made for the continuation
    mock_post.assert_called_once()

def test_parse_comment_with_full_metadata(fetcher, initial_comment_data, mocker):
    """ Tests that we can extract the full set of desired metadata from a comment. """
    mocker.patch.object(fetcher, '_find_comment_page_continuation', return_value=None)
    mocker.patch.object(
        fetcher,
        '_parse_comments',
        return_value=[
            {
                "author_channel_id": "UC-test",
                "author_avatar_url": "https://ggpht.com/a/test",
                "reply_count": 1,
                "is_pinned": False,
                "author_badges": []
            }
        ]
    )
    mocker.patch.object(fetcher, '_extract_initial_data', return_value=initial_comment_data)
    mocker.patch.object(fetcher._client, 'get', return_value=mocker.Mock(status_code=200, text='ytcfg.set({"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {"client": {"clientName": "WEB", "clientVersion": "2.20210721.00.00"}}});'))

    comments = list(fetcher.get_comments("any_id", limit=1))
    assert len(comments) > 0
    first_comment = comments[0]
    assert "author_channel_id" in first_comment
    assert "author_avatar_url" in first_comment
    assert "reply_count" in first_comment
    assert "is_pinned" in first_comment
    assert "author_badges" in first_comment
    assert isinstance(first_comment["author_channel_id"], str)
    assert isinstance(first_comment["author_avatar_url"], str)
    assert isinstance(first_comment["reply_count"], int)
    assert isinstance(first_comment["is_pinned"], bool)
    assert isinstance(first_comment["author_badges"], list)
    assert first_comment["author_channel_id"].startswith("UC")
    assert "ggpht.com" in first_comment["author_avatar_url"]

def test_comment_author_badge_extraction(fetcher):
    """Tests that author badges are extracted from comments."""
    comment_payload_with_badge = {
        "authorBadges": [{"metadataBadgeRenderer": {"icon": {"iconType": "CHECK_CIRCLE"}}}]
    }
    comment_data = fetcher._parse_comment_payload(comment_payload_with_badge)
    assert "CHECK_CIRCLE" in comment_data["author_badges"]

def test_pinned_comment_detection(fetcher):
    """Test that pinned comments are properly identified."""
    comment_payload_pinned = {"pinnedCommentBadge": {"some": "data"}}
    comment_data = fetcher._parse_comment_payload(comment_payload_pinned)
    assert comment_data["is_pinned"] is True

def test_is_reply_flag(fetcher):
    """Tests that the is_reply flag is correctly set."""
    reply_payload = {"isReply": True, "parentId": "parent123"}
    comment_data = fetcher._parse_comment_payload(reply_payload)
    assert comment_data["is_reply"] is True
    assert comment_data["parent_id"] == "parent123"

def test_get_comments_handles_unavailable_video(fetcher, mocker):
    """ Test that get_comments raises VideoUnavailableError for a 404. """
    mocker.patch.object(fetcher._client, 'get', side_effect=httpx.HTTPStatusError("404 Not Found", request=mocker.MagicMock(), response=mocker.MagicMock(status_code=404)))
    with pytest.raises(VideoUnavailableError):
        list(fetcher.get_comments("invalidVideoId"))

def test_progress_callback_is_called(fetcher, video_page_html, initial_comment_data, continuation_json, mocker):
    """ Verify that the progress callback is called for each comment. """
    mocker.patch.object(fetcher, '_extract_initial_data', return_value=initial_comment_data)
    mocker.patch.object(fetcher, '_parse_comments', side_effect=[[{"text": "a"}] * 20, [{"text": "b"}] * 5])
    mocker.patch.object(fetcher._client, 'get', return_value=mocker.Mock(status_code=200, text=video_page_html))
    mocker.patch.object(fetcher._client, 'post', return_value=mocker.Mock(status_code=200, json=lambda: continuation_json))
    mocker.patch.object(fetcher, '_get_sort_endpoints', return_value={"top": ("fake_token", None, None)})
    mocker.patch.object(fetcher, '_find_api_key_and_context', return_value=("key", "context"))
    mocker.patch.object(fetcher, '_find_comment_page_continuation', side_effect=['fake_token', None])

    callback = mocker.Mock()
    # We will limit to 25 to get both initial (20) and continuation (5) comments
    comments = list(fetcher.get_comments("any_id", limit=25, progress_callback=callback))

    num_comments = len(comments)
    assert num_comments == 25
    assert callback.call_count == 25
    # The callback is called with the cumulative count
    callback.assert_called_with(25)

def test_get_comments_with_reply_tokens(fetcher, video_page_html, initial_comment_data, continuation_json, mocker):
    """ Verify that get_comments with include_reply_continuation=True includes reply tokens. """
    mocker.patch.object(fetcher, '_extract_initial_data', return_value=initial_comment_data)
    mocker.patch.object(fetcher, '_get_sort_endpoints', return_value={"top": ("fake_token", None, None)})
    mocker.patch.object(fetcher, '_find_api_key_and_context', return_value=("key", "context"))
    mocker.patch.object(fetcher._client, 'post', return_value=mocker.Mock(status_code=200, json=lambda: continuation_json))
    mocker.patch.object(fetcher, '_find_comment_page_continuation', return_value=None)
    mocker.patch.object(fetcher, '_parse_comments', return_value=[
        {"id": "Ugw_V_4Q3gmI1gA03f54AaABAg"},
        {"id": "Ugybl-106x8gvu3k4h54AaABAg"}
    ])

    # Mock the reply continuation extraction. The key is a real comment ID from the initial_comment_data fixture.
    mocker.patch.object(fetcher, '_extract_reply_continuations_for_comments', return_value={"Ugw_V_4Q3gmI1gA03f54AaABAg": "reply_token_1"})

    comments = list(fetcher.get_comments("any_id", limit=25, include_reply_continuation=True))

    assert any("reply_continuation_token" in c for c in comments)
    first_with_token = next(c for c in comments if "reply_continuation_token" in c)
    assert first_with_token["id"] == "Ugw_V_4Q3gmI1gA03f54AaABAg"
    assert first_with_token["reply_continuation_token"] == "reply_token_1"

def test_get_comment_replies(fetcher, reply_json, mocker):
    """ Verify get_comment_replies fetches replies for a specific comment thread. """
    mocker.patch.object(fetcher._client, 'get', return_value=mocker.Mock(status_code=200, text="<html></html>"))
    mocker.patch.object(fetcher, '_find_api_key_and_context', return_value=("key", "context"))
    mocker.patch.object(fetcher._client, 'post', return_value=mocker.Mock(status_code=200, json=lambda: reply_json))
    mocker.patch.object(fetcher, '_find_comment_page_continuation', return_value=None)

    replies = list(fetcher.get_comment_replies("any_id", "fake_token", limit=10))

    assert len(replies) > 0
    assert "is_reply" in replies[0]
    assert replies[0]["is_reply"] is True
    assert replies[0]["parent_id"] == "Ugw_V_4Q3gmI1gA03f54AaABAg"

def test_get_comments_since_date_requires_recent_sort(fetcher):
    """ Verify that using since_date without sort_by='recent' raises a ValueError. """
    with pytest.raises(ValueError, match="`since_date` can only be used with `sort_by='recent'`"):
        list(fetcher.get_comments("any_id", sort_by="top", since_date=date(2024, 1, 1)))

def test_get_comments_since_date_stops_pagination(fetcher, mocker):
    """ Verify that pagination stops when a comment older than since_date is found. """
    mocker.patch.object(fetcher, '_get_sort_endpoints', return_value={"recent": ("fake_token", None, None)})
    mocker.patch.object(fetcher, '_extract_initial_data', return_value={"contents": {"twoColumnWatchNextResults": {"results": {"results": {"contents": [{"itemSectionRenderer": {"contents": [{"continuationItemRenderer": {"continuationEndpoint": {"commentActionButtonsRenderer": {"sortMenu": {"sortFilterSubMenuRenderer": {"subMenuItems": [{"title": "Recent comments", "serviceEndpoint": {"continuationCommand": {"token": "fake_token"}}}]}}}}}}]}}]}}}}})
    mocker.patch.object(fetcher, '_find_api_key_and_context', return_value=("key", "context"))

    page1_comments = [{"id": "1", "publish_date": date(2024, 7, 15)}, {"id": "2", "publish_date": date(2024, 7, 14)}]
    page2_comments = [{"id": "3", "publish_date": date(2024, 7, 13)}, {"id": "4", "publish_date": date(2024, 7, 12)}]

    mocker.patch.object(fetcher._client, 'post', side_effect=[
        mocker.Mock(status_code=200, json=lambda: {"response": "page1"}),
        mocker.Mock(status_code=200, json=lambda: {"response": "page2"}),
    ])
    mocker.patch.object(fetcher, '_parse_comments', side_effect=[page1_comments, page2_comments])
    mocker.patch.object(fetcher, '_find_comment_page_continuation', side_effect=["next_page_token", None])

    comments = list(fetcher.get_comments("any_id", sort_by="recent", since_date=date(2024, 7, 13)))

    assert len(comments) == 3
    assert [c['id'] for c in comments] == ["1", "2", "3"]
