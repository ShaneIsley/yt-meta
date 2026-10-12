"""Custom exceptions for the yt-meta library."""


class YtMetaError(Exception):
    """
    Base exception for all errors raised by the yt-meta library.

    This exception can store context like a `video_id` or `channel_url` to
    make debugging easier.
    """

    def __init__(self, message, video_id=None, channel_url=None, playlist_id=None):
        super().__init__(message)
        self.video_id = video_id
        self.channel_url = channel_url
        self.playlist_id = playlist_id

    def __str__(self):
        details = []
        if self.video_id:
            details.append(f"video_id='{self.video_id}'")
        if self.channel_url:
            details.append(f"channel_url='{self.channel_url}'")
        if self.playlist_id:
            details.append(f"playlist_id='{self.playlist_id}'")

        if details:
            return f"{super().__str__()} ({', '.join(details)})"
        return super().__str__()


class MetadataParsingError(YtMetaError):
    """
    Raised when essential metadata cannot be found or parsed from the page.

    This typically occurs if YouTube changes its page structure, and the
    scraper can no longer find the `ytInitialData` or `ytcfg` JSON blobs.
    """

    pass


class VideoUnavailableError(YtMetaError):
    """
    Raised when a page or API request fails: a network error, or an HTTP
    error status (404, or 429/5xx after retries).

    An invalid URL raises ValueError instead. A video that is private,
    deleted or members-only is not an error: get_video_metadata returns
    it with ``status="unavailable"``.
    """

    pass
