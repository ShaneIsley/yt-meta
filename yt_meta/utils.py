# yt_meta/utils.py


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
    
    if 'K' in vote_str:
        return int(float(vote_str.replace('K', '')) * 1_000)
    elif 'M' in vote_str:
        return int(float(vote_str.replace('M', '')) * 1_000_000)
    elif vote_str.isdigit():
        return int(vote_str)
    return 0
