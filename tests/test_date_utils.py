# tests/test_date_utils.py
from datetime import date, timedelta

from yt_meta.date_utils import parse_relative_date_string


def test_parse_shorthand_days():
    """Tests the shorthand 'd' notation."""
    expected = date.today() - timedelta(days=5)
    assert parse_relative_date_string("5d") == expected
    assert parse_relative_date_string(" 5d ") == expected


def test_parse_shorthand_weeks():
    """Tests the shorthand 'w' notation."""
    expected = date.today() - timedelta(weeks=2)
    assert parse_relative_date_string("2w") == expected


def test_parse_shorthand_months():
    """Tests the shorthand 'm' notation (approx. 30 days)."""
    expected = date.today() - timedelta(days=3 * 30)
    assert parse_relative_date_string("3m") == expected


def test_parse_shorthand_years():
    """Tests the shorthand 'y' notation (approx. 365 days)."""
    expected = date.today() - timedelta(days=1 * 365)
    assert parse_relative_date_string("1y") == expected


def test_parse_human_readable_days():
    """Tests the human-readable 'day ago' notation."""
    expected = date.today() - timedelta(days=1)
    assert parse_relative_date_string("1 day ago") == expected
    assert parse_relative_date_string("1 days ago") == expected


def test_parse_human_readable_weeks():
    """Tests the human-readable 'week ago' notation."""
    expected = date.today() - timedelta(weeks=3)
    assert parse_relative_date_string("3 week ago") == expected
    assert parse_relative_date_string("3 weeks ago") == expected


def test_parse_human_readable_months():
    """Tests the human-readable 'month ago' notation."""
    expected = date.today() - timedelta(days=6 * 30)
    assert parse_relative_date_string("6 month ago") == expected
    assert parse_relative_date_string("6 months ago") == expected


def test_parse_human_readable_years():
    """Tests the human-readable 'year ago' notation."""
    expected = date.today() - timedelta(days=2 * 365)
    assert parse_relative_date_string("2 year ago") == expected
    assert parse_relative_date_string("2 years ago") == expected


def test_parse_invalid_string_returns_today():
    """Tests that an invalid or empty string returns today's date."""
    assert parse_relative_date_string("invalid date") == date.today()
    assert parse_relative_date_string("") == date.today()
    assert parse_relative_date_string(None) == date.today()
