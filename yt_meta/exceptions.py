"""Custom exceptions for the YtMeta application."""


class YtMetaError(Exception):
    """Base exception for all errors raised by YtMeta."""

    def __init__(self, message, video_id=None, channel_url=None):
        super().__init__(message)
        self.video_id = video_id
        self.channel_url = channel_url

    def __str__(self):
        details = []
        if self.video_id:
            details.append(f"video_id='{self.video_id}'")
        if self.channel_url:
            details.append(f"channel_url='{self.channel_url}'")

        if details:
            return f"{super().__str__()} ({', '.join(details)})"
        return super().__str__()


class MetadataParsingError(YtMetaError):
    """Raised when metadata cannot be parsed from the page."""

    pass


class VideoUnavailableError(YtMetaError):
    """Raised when a video is unavailable or the page cannot be fetched."""

    pass
