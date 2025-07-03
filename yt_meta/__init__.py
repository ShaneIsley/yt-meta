# yt_meta/__init__.py

from .client import YtMeta
from .comment_api_client import CommentAPIClient
from .comment_fetcher import BestCommentFetcher, CommentFetcher
from .comment_parser import CommentParser
from .date_utils import parse_relative_date_string
from .exceptions import MetadataParsingError, VideoUnavailableError

__version__ = "0.3.1"

__all__ = [
    "YtMeta",
    "MetadataParsingError",
    "VideoUnavailableError",
    "parse_relative_date_string",
    "CommentFetcher",
    "BestCommentFetcher",  # Backward compatibility
    "CommentAPIClient",
    "CommentParser",
]
