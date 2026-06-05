# yt_meta/date_utils.py
import re
from datetime import date, datetime, timedelta

import dateparser


def parse_relative_date_string(date_str: str) -> date:
    """
    Parses a date string into a date object.

    Handles three formats:
    1. Shorthand notation (e.g., "1d", "2w", "3m", "4y" for days, weeks,
       months, and years).
    2. Human-readable notation (e.g., "1 day ago", "2 weeks ago").
    3. Absolute dates parseable by ``dateparser`` (e.g., "2023-01-01",
       "January 1 2023").

    Notes:
    - Months are approximated as 30 days, years as 365 days.
    - Non-str inputs (e.g. ``None``) return today's date as a defensive
      fallback for callers using ``dict.get(...)``-style lookups.
    - Unrecognized strings raise ``ValueError`` — failing loudly is preferred
      to silently returning today, which corrupted downstream date filters
      (see review H2).
    """
    if not isinstance(date_str, str):
        return datetime.today().date()

    date_str = date_str.lower().strip()

    shorthand_match = re.match(r"(\d+)\s*([dwmy])", date_str)
    if shorthand_match:
        value = int(shorthand_match.group(1))
        unit = shorthand_match.group(2)

        if unit == "d":
            return datetime.today().date() - timedelta(days=value)
        elif unit == "w":
            return datetime.today().date() - timedelta(weeks=value)
        elif unit == "m":
            return datetime.today().date() - timedelta(days=value * 30)
        elif unit == "y":
            return datetime.today().date() - timedelta(days=value * 365)

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

    parsed = dateparser.parse(date_str, settings={"PREFER_DATES_FROM": "past"})
    if parsed is not None:
        return parsed.date() if isinstance(parsed, datetime) else parsed

    raise ValueError(f"Could not parse date string: {date_str!r}")


parse_human_readable_date = parse_relative_date_string
