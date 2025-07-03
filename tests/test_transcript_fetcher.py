from unittest.mock import MagicMock, patch

import pytest

from yt_meta.transcript_fetcher import TranscriptFetcher


@patch("yt_meta.transcript_fetcher.YouTubeTranscriptApi")
def test_get_transcript_success(mock_api_class):
    """
    Test that get_transcript successfully fetches and returns a transcript.
    """
    # Arrange
    mock_api_instance = MagicMock()
    mock_transcript_list = MagicMock()
    mock_transcript = MagicMock()

    mock_snippet = MagicMock()
    mock_snippet.text = "hello"
    mock_snippet.start = 0.0
    mock_snippet.duration = 1.0

    mock_transcript.fetch.return_value = [mock_snippet]
    mock_transcript_list.find_transcript.return_value = mock_transcript
    mock_api_instance.list.return_value = mock_transcript_list
    mock_api_class.return_value = mock_api_instance

    fetcher = TranscriptFetcher()
    video_id = "test_video_id"

    # Act
    result = fetcher.get_transcript(video_id)

    # Assert
    assert result == [{"text": "hello", "start": 0.0, "duration": 1.0}]
    mock_api_instance.list.assert_called_once_with(video_id)
    mock_transcript_list.find_transcript.assert_called_once_with(["en"])
    mock_transcript.fetch.assert_called_once()


@patch("yt_meta.transcript_fetcher.YouTubeTranscriptApi")
def test_get_transcript_failure(mock_api_class):
    """
    Test that get_transcript returns an empty list when the API call fails.
    """
    # Arrange
    mock_api_instance = MagicMock()
    mock_api_instance.list.side_effect = Exception("API error")
    mock_api_class.return_value = mock_api_instance

    fetcher = TranscriptFetcher()
    video_id = "test_video_id"

    # Act
    result = fetcher.get_transcript(video_id)

    # Assert
    assert result == []
    mock_api_instance.list.assert_called_once_with(video_id)


@pytest.mark.integration
def test_get_video_transcript_integration():
    """
    Test that get_video_transcript fetches a real transcript from YouTube.
    """
    # Arrange
    from yt_meta.client import YtMeta

    client = YtMeta()
    video_id = "dQw4w9WgXcQ"  # A short video with a known transcript

    # Act
    transcript = client.get_video_transcript(video_id)

    # Assert
    assert isinstance(transcript, list)
    assert len(transcript) > 0
    first_snippet = transcript[0]
    assert "text" in first_snippet
    assert "start" in first_snippet
    assert "duration" in first_snippet 