import logging
from typing import Dict, List
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)


class TranscriptFetcher:
    """A fetcher for retrieving video transcripts from YouTube."""

    def get_transcript(self, video_id: str, languages: List[str] = None) -> List[Dict]:
        """
        Fetches the transcript for a given video ID.

        Args:
            video_id: The ID of the YouTube video.
            languages: A list of language codes to prioritize (e.g., ['en', 'de']).
                       If None, it will default to English.

        Returns:
            A list of dictionary objects, where each object represents a
            transcript snippet with 'text', 'start', and 'duration' keys.
            Returns an empty list if the transcript cannot be fetched.
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
        except Exception as e:
            logger.error(f"Could not fetch transcript for {video_id}: {e}")
            return [] 