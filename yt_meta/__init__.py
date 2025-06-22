# yt_meta/__init__.py

from .client import YtMetaClient
from .date_utils import parse_relative_date_string
from .exceptions import MetadataParsingError, VideoUnavailableError

__version__ = "0.1.0"

__all__ = [
    "YtMetaClient",
    "MetadataParsingError",
    "VideoUnavailableError",
    "parse_relative_date_string",
]
