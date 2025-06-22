# yt_meta/utils.py


def _deep_get(dictionary, keys, default=None):
    """
    Safely access nested dictionary keys, including list indices.
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
