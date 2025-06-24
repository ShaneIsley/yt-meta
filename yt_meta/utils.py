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
