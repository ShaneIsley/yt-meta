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
    """M-d/M20 (0.8.0): only the library's documented no-transcript
    exceptions map to []; a generic failure must propagate (it used to
    be swallowed, making rate limits look like 'no transcript')."""
    mock_api_instance = MagicMock()
    mock_api_instance.list.side_effect = Exception("API error")
    mock_api_class.return_value = mock_api_instance

    fetcher = TranscriptFetcher()
    with pytest.raises(Exception, match="API error"):
        fetcher.get_transcript("test_video_id")


def test_m20_no_transcript_returns_empty(mocker):
    """M20: 'no transcript exists' is the documented empty-list case.
    Raise the dependency's REAL exception type (R1) — not a stand-in."""
    from unittest.mock import MagicMock

    from youtube_transcript_api import NoTranscriptFound

    from yt_meta.transcript_fetcher import TranscriptFetcher

    fetcher = TranscriptFetcher()
    exc = NoTranscriptFound("vid123", ["en"], MagicMock())
    mocker.patch(
        "yt_meta.transcript_fetcher.YouTubeTranscriptApi"
    ).return_value.list.side_effect = exc
    assert fetcher.get_transcript("vid123") == []


def test_m20_transcripts_disabled_returns_empty(mocker):
    from youtube_transcript_api import TranscriptsDisabled

    from yt_meta.transcript_fetcher import TranscriptFetcher

    fetcher = TranscriptFetcher()
    mocker.patch(
        "yt_meta.transcript_fetcher.YouTubeTranscriptApi"
    ).return_value.list.side_effect = TranscriptsDisabled("vid123")
    assert fetcher.get_transcript("vid123") == []


def test_m20_unexpected_error_propagates(mocker):
    """REGRESSION (M-d/M20): the bare `except Exception: return []` made
    a rate-limit, network failure, or parser bug indistinguishable from
    'this video has no transcript'. Only the library's documented
    could-not-retrieve exceptions may map to []; everything else
    propagates."""
    import pytest as _pytest

    from yt_meta.transcript_fetcher import TranscriptFetcher

    fetcher = TranscriptFetcher()
    mocker.patch(
        "yt_meta.transcript_fetcher.YouTubeTranscriptApi"
    ).return_value.list.side_effect = RuntimeError("YouTube blocked the request")
    with _pytest.raises(RuntimeError):
        fetcher.get_transcript("vid123")
