# yt_meta/utils.py

import re
from urllib.parse import urlparse

# Canonical YouTube video IDs are 11 characters from [A-Za-z0-9_-].
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Hostnames the library is willing to issue requests to. Anything else
# (evil.example.com, attacker.test, IDN-spoofed lookalikes) is rejected
# at the boundary before the session.get happens.
_YOUTUBE_HOSTNAMES = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
})


def _is_valid_video_id(s: str) -> bool:
    return isinstance(s, str) and _VIDEO_ID_RE.fullmatch(s) is not None


def validate_youtube_url(url: str) -> str:
    """Raise ValueError unless ``url`` points to a known YouTube hostname.

    Defensive guard at the network boundary against SSRF / open-redirect
    style abuse when a channel or playlist URL is forwarded from
    untrusted input. Returns the URL unchanged on success so this can be
    used inline as ``self.session.get(validate_youtube_url(url))``.
    """
    if not isinstance(url, str):
        raise ValueError(f"Expected str URL, got {type(url).__name__}")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTNAMES:
        raise ValueError(
            f"URL hostname {host!r} is not a known YouTube domain. "
            f"Expected one of {sorted(_YOUTUBE_HOSTNAMES)}."
        )
    return url


def _deep_get(dictionary, keys, default=None):
    """
    Safely access nested dictionary keys and list indices.

    This function allows you to retrieve a value from a nested structure of
    dictionaries and lists using a dot-separated string of keys or a list
    of keys/indices.

    Args:
        dictionary (dict or list): The nested structure to search.
        keys (str or list): A dot-separated string (e.g., "a.b.0.c") or a
                            list of keys and integer indices.
        default: The value to return if any key is not found. Defaults to None.

    Returns:
        The value found at the specified path, or the default value if not found.
    """
    if dictionary is None:
        return default
    if not isinstance(keys, list):
        keys = keys.split(".")

    current_val = dictionary
    for key in keys:
        if isinstance(current_val, list) and key.isdigit():
            idx = int(key)
            if 0 <= idx < len(current_val):
                current_val = current_val[idx]
            else:
                return default
        elif isinstance(current_val, dict):
            current_val = current_val.get(key)
            if current_val is None:
                return default
        else:
            return default
    return current_val


def parse_vote_count(vote_str: str) -> int:
    """
    Parses a vote count string (e.g., '1.2K', '25', '1M') into an integer.
    """
    if not isinstance(vote_str, str):
        return 0
    vote_str = vote_str.strip().upper()
    if not vote_str:
        return 0

    if "K" in vote_str:
        return int(float(vote_str.replace("K", "")) * 1_000)
    elif "M" in vote_str:
        return int(float(vote_str.replace("M", "")) * 1_000_000)
    elif vote_str.isdigit():
        return int(vote_str)
    return 0


def extract_video_id(youtube_url: str) -> str:
    """
    Extract the canonical 11-character video ID from a YouTube URL or
    bare ID.

    Accepts ``watch?v=ID``, ``/shorts/ID``, ``youtu.be/ID``, and a bare
    11-char ID. Every return path validates the extracted ID against
    ``[A-Za-z0-9_-]{11}``. The previous pass-through fallback that
    accepted any non-``http`` string (M13) is removed — it allowed
    "test_id", "../etc/passwd", and similar to flow into cache keys.

    Raises ValueError if the ID can't be extracted or fails validation.
    """
    if not isinstance(youtube_url, str) or not youtube_url:
        raise ValueError(f"Could not extract video ID from: {youtube_url!r}")

    # Bare 11-char ID — fast path.
    if _is_valid_video_id(youtube_url):
        return youtube_url

    candidate: str | None = None
    if "v=" in youtube_url:
        candidate = youtube_url.split("v=")[1].split("&")[0]
    elif "/shorts/" in youtube_url:
        candidate = youtube_url.split("/shorts/")[1].split("?")[0]
    elif "youtu.be/" in youtube_url:
        candidate = youtube_url.split("youtu.be/")[1].split("?")[0]

    if candidate is None:
        raise ValueError(f"Could not extract video ID from URL: {youtube_url}")
    if not _is_valid_video_id(candidate):
        raise ValueError(
            f"Invalid video ID {candidate!r} extracted from URL: "
            f"{youtube_url} (expected 11 chars [A-Za-z0-9_-])"
        )
    return candidate
