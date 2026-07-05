import logging

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

logger = logging.getLogger(__name__)

# The library's documented "this video has no transcript to give you"
# outcomes. These — and only these — map to an empty list. M-d/M20: the
# previous bare `except Exception: return []` also swallowed rate
# limits, network failures, and parser bugs, making them
# indistinguishable from "no transcript".
_NO_TRANSCRIPT_ERRORS = (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable)


class TranscriptFetcher:
    """A fetcher for retrieving video transcripts from YouTube."""

    def get_transcript(
        self, video_id: str, languages: list[str] | None = None
    ) -> list[dict]:
        """
        Fetches the transcript for a given video ID.

        Args:
            video_id: The ID of the YouTube video.
            languages: A list of language codes to prioritize (e.g., ['en', 'de']).
                       If None, it will default to English.

        Returns:
            A list of dictionary objects, where each object represents a
            transcript snippet with 'text', 'start', and 'duration' keys.
            Returns an empty list when the video has no transcript to
            offer (none found for the requested languages, transcripts
            disabled, or the video is unavailable).

        Raises:
            Any other error — rate limiting, network failure, an
            upstream shape change — propagates so it can't be mistaken
            for "no transcript".
        """
        if languages is None:
            languages = ["en"]
        try:
            transcript_list = YouTubeTranscriptApi().list(video_id)
            transcript = transcript_list.find_transcript(languages)
            fetched_transcript = transcript.fetch()
            return [
                {"text": snippet.text, "start": snippet.start, "duration": snippet.duration}
                for snippet in fetched_transcript
            ]
        except _NO_TRANSCRIPT_ERRORS as e:
            logger.info(f"No transcript available for {video_id}: {type(e).__name__}")
            return []
