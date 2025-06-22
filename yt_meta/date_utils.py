# yt_meta/date_utils.py
import re
from datetime import date, datetime, timedelta


def parse_relative_date_string(date_str: str) -> date:
    """
    Parses a relative date string (e.g., "1d", "2 weeks ago") into a date object.
    Returns today's date if the string is invalid.
    """
    if not isinstance(date_str, str):
        return datetime.today().date()

    date_str = date_str.lower().strip()

    # --- Handle Shorthand Notation (e.g., "1d", "2w", "3m", "4y") ---
    shorthand_match = re.match(r"(\d+)\s*([dwmy])", date_str)
    if shorthand_match:
        value = int(shorthand_match.group(1))
        unit = shorthand_match.group(2)

        if unit == "d":
            return datetime.today().date() - timedelta(days=value)
        elif unit == "w":
            return datetime.today().date() - timedelta(weeks=value)
        elif unit == "m":
            # Approximate months as 30 days
            return datetime.today().date() - timedelta(days=value * 30)
        elif unit == "y":
            # Approximate years as 365 days
            return datetime.today().date() - timedelta(days=value * 365)

    # --- Handle Human-Readable Notation (e.g., "1 day ago", "2 weeks ago") ---
    human_readable_match = re.match(r"(\d+)\s*(day|week|month|year)s?\s*ago", date_str)
    if human_readable_match:
        value = int(human_readable_match.group(1))
        unit = human_readable_match.group(2)

        if unit == "day":
            return datetime.today().date() - timedelta(days=value)
        elif unit == "week":
            return datetime.today().date() - timedelta(weeks=value)
        elif unit == "month":
            return datetime.today().date() - timedelta(days=value * 30)
        elif unit == "year":
            return datetime.today().date() - timedelta(days=value * 365)

    # Fallback for unrecognized formats
    return datetime.today().date()
