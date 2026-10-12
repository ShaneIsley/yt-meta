import logging

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from ._retry import RETRYABLE_STATUS
from .utils import CONSENT_COOKIE

logger = logging.getLogger(__name__)

# The library's documented "this video has no transcript to give you"
# outcomes. These — and only these — map to an empty list. M-d/M20: the
# previous bare `except Exception: return []` also swallowed rate
# limits, network failures, and parser bugs, making them
# indistinguishable from "no transcript".
_NO_TRANSCRIPT_ERRORS = (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable)


class TranscriptFetcher:
    """A fetcher for retrieving video transcripts from YouTube.

    youtube_transcript_api makes its own requests through a
    ``requests.Session``, so it can't use YtMeta's httpx session. The
    session built here mirrors that one's behavior: the consent cookie
    when ``accept_cookies`` is set, and retry with backoff on 429/5xx,
    honoring Retry-After. A new session per call, because the library
    documents its client as not thread-safe.
    """

    def __init__(self, accept_cookies: bool = False, retries: int = 3):
        self.accept_cookies = accept_cookies
        self.retries = retries

    def _make_session(self) -> Session:
        session = Session()
        if self.accept_cookies:
            session.cookies.set(*CONSENT_COOKIE, domain=".youtube.com")
        retry = Retry(
            total=self.retries,
            backoff_factor=1.0,
            status_forcelist=sorted(RETRYABLE_STATUS),
            allowed_methods=None,  # the transcript API also POSTs
            respect_retry_after_header=True,
            # Return the last response instead of raising RetryError, so
            # youtube_transcript_api reports a persistent 429 the same
            # way it did before.
            raise_on_status=False,
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

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
            api = YouTubeTranscriptApi(http_client=self._make_session())
            transcript_list = api.list(video_id)
            transcript = transcript_list.find_transcript(languages)
            fetched_transcript = transcript.fetch()
            return [
                {"text": snippet.text, "start": snippet.start, "duration": snippet.duration}
                for snippet in fetched_transcript
            ]
        except _NO_TRANSCRIPT_ERRORS as e:
            logger.info(f"No transcript available for {video_id}: {type(e).__name__}")
            return []
