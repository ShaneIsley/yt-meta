from pathlib import Path
import json
import re
import pytest
import httpx

from yt_meta.comment_fetcher import CommentFetcher

FIXTURES_PATH = Path(__file__).parent / "fixtures"

@pytest.fixture
def fetcher():
    return CommentFetcher()

@pytest.fixture
def video_page_html():
    return (FIXTURES_PATH / "B68agR-OeJM.html").read_text()

@pytest.fixture
def continuation_json():
    return json.loads((FIXTURES_PATH / "comment_continuation_response.json").read_text())

def test_extract_initial_data_and_tokens(fetcher, video_page_html):
    initial_data = fetcher._extract_initial_data(video_page_html)
    assert isinstance(initial_data, dict)
    assert "contents" in initial_data

    continuation_token = fetcher._find_continuation_token(initial_data)
    assert isinstance(continuation_token, str)
    assert len(continuation_token) > 50

    api_key, context = fetcher._find_api_key_and_context(video_page_html)
    assert isinstance(api_key, str)
    assert api_key.startswith("AIza")
    assert isinstance(context, dict)
    assert "client" in context

def test_parse_initial_comments(fetcher, video_page_html):
    initial_data = fetcher._extract_initial_data(video_page_html)
    comments = fetcher._parse_comments(initial_data)
    
    assert isinstance(comments, list)
    assert len(comments) > 0
    
    first_comment = comments[0]
    assert "id" in first_comment
    assert "text" in first_comment
    assert "author" in first_comment
    assert "likes" in first_comment
    assert "published_time" in first_comment

def test_parse_continuation_comments(fetcher, continuation_json):
    comments = fetcher._parse_comments(continuation_json)
    assert isinstance(comments, list)
    assert len(comments) > 0
    
    first_comment = comments[0]
    assert "id" in first_comment
    
    next_token = fetcher._find_continuation_token(continuation_json)
    assert isinstance(next_token, str)
    assert len(next_token) > 50

def test_get_comments_end_to_end(fetcher, video_page_html, continuation_json, mocker):
    """
    Tests the full get_comments generator workflow, mocking all network requests.
    """
    # 1. Mock the responses
    mock_get_response = mocker.Mock()
    mock_get_response.text = video_page_html
    mock_get_response.raise_for_status = mocker.Mock()

    mock_post_response = mocker.Mock()
    mock_post_response.json.return_value = continuation_json
    mock_post_response.raise_for_status = mocker.Mock()
    
    # This second post response will have no continuation, ending the loop
    mock_post_response_final = mocker.Mock()
    final_json = continuation_json.copy()
    # Remove the continuation token from the second response to stop the loop
    del final_json["onResponseReceivedEndpoints"][0]["appendContinuationItemsAction"]["continuationItems"][1]
    mock_post_response_final.json.return_value = final_json
    mock_post_response_final.raise_for_status = mocker.Mock()


    # 2. Patch the httpx client
    mock_client = mocker.patch('httpx.Client', autospec=True)
    mock_client.return_value.__enter__.return_value.get.return_value = mock_get_response
    mock_client.return_value.__enter__.return_value.post.side_effect = [mock_post_response, mock_post_response_final]

    # 3. Call the generator and collect results
    comments_generator = fetcher.get_comments("B68agR-OeJM")
    all_comments = list(comments_generator)

    # 4. Assert results
    # (Number of comments from initial page + comments from one continuation)
    assert len(all_comments) > 20 
    assert all_comments[0]['id'] is not None
    assert all_comments[-1]['id'] is not None

    # 5. Assert that the mocks were called correctly
    mock_client.return_value.__enter__.return_value.get.assert_called_once_with('https://www.youtube.com/watch?v=B68agR-OeJM')
    
    post_calls = mock_client.return_value.__enter__.return_value.post.call_args_list
    assert len(post_calls) == 2
    
    first_post_args, first_post_kwargs = post_calls[0]
    assert "https://www.youtube.com/youtubei/v1/next?key=" in first_post_args[0]
    assert "json" in first_post_kwargs
    assert "continuation" in first_post_kwargs["json"]

def test_get_sort_endpoints(fetcher, video_page_html):
    """
    Tests that we can correctly extract the sorting endpoints from the initial data.
    """
    initial_data = fetcher._extract_initial_data(video_page_html)
    sort_endpoints = fetcher._get_sort_endpoints(initial_data)

    assert "top" in sort_endpoints
    assert "recent" in sort_endpoints

    top_token = sort_endpoints["top"]["continuationCommand"]["token"]
    recent_token = sort_endpoints["recent"]["continuationCommand"]["token"]

    assert isinstance(top_token, str) and len(top_token) > 50
    assert isinstance(recent_token, str) and len(recent_token) > 50
    assert top_token != recent_token

def test_parse_comment_with_full_metadata(fetcher, continuation_json):
    """
    Tests that we can extract the full set of desired metadata from a comment.
    """
    comments = fetcher._parse_comments(continuation_json)
    
    assert len(comments) > 0
    first_comment = comments[0]

    # Assert that the new keys exist
    assert "author_channel_id" in first_comment
    assert "author_avatar_url" in first_comment
    assert "reply_count" in first_comment

    # Assert that the data types are correct
    assert isinstance(first_comment["author_channel_id"], str)
    assert isinstance(first_comment["author_avatar_url"], str)
    assert isinstance(first_comment["reply_count"], int)

    # Assert that the values are plausible
    assert first_comment["author_channel_id"].startswith("UC")
    assert "ggpht.com" in first_comment["author_avatar_url"] 