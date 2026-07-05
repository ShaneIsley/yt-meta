from datetime import date

import pytest

from yt_meta.validators import validate_filters


def test_validate_filters_invalid_field():
    """Test that an unknown filter field raises a ValueError."""
    filters = {"non_existent_field": {"eq": 1}}
    with pytest.raises(ValueError, match="Unknown filter field"):
        validate_filters(filters)


def test_m22_validate_filters_accepts_after_before_for_publish_date():
    """REGRESSION (M22): _check_date_condition has always supported the
    readable aliases after/before (== gt/lt), and test_apply_filters_
    publish_date used them — but FILTER_SCHEMA only listed gt/gte/lt/
    lte/eq, so validate_filters REJECTED them. A user following the
    test's pattern through the real (validated) code path hit a
    ValueError. M22 adds after/before to the publish_date operators so
    the whole stack agrees.
    """
    # These must not raise now.
    validate_filters({"publish_date": {"after": "2023-01-01"}})
    validate_filters({"publish_date": {"before": "2023-01-01"}})
    validate_filters({"publish_date": {"after": date(2023, 1, 1)}})


def test_m22_after_before_still_rejected_on_numeric_fields():
    """REGRESSION (M22): the aliases are date-only. Numeric fields like
    view_count must still reject after/before — they're not numeric
    operators.
    """
    with pytest.raises(ValueError, match="Invalid operator"):
        validate_filters({"view_count": {"after": 1000}})


def test_validate_filters_invalid_operator():
    """Test that an invalid operator for a known field raises a ValueError."""
    # Numerical field with a text operator
    filters = {"view_count": {"contains": "text"}}
    with pytest.raises(
        ValueError, match="Invalid operator 'contains' for field 'view_count'"
    ):
        validate_filters(filters)

    # Text field with a numerical operator
    filters = {"title": {"gt": 100}}
    with pytest.raises(ValueError, match="Invalid operator 'gt' for field 'title'"):
        validate_filters(filters)


def test_validate_filters_invalid_value_type():
    """Test that an invalid value type for an operator raises a TypeError."""
    # Numerical operator with a string value
    filters = {"view_count": {"gt": "not_a_number"}}
    with pytest.raises(TypeError, match="Invalid value type for 'view_count' filter"):
        validate_filters(filters)

    # Text operator with a numerical value
    filters = {"title": {"contains": 123}}
    with pytest.raises(TypeError, match="Invalid value type for 'title' filter"):
        validate_filters(filters)

    # List operator with a string value
    filters = {"keywords": {"contains_any": "not_a_list"}}
    with pytest.raises(TypeError, match="Invalid value type for 'keywords' filter"):
        validate_filters(filters)


def test_validate_filters_valid_filters():
    """Test that a valid set of filters passes validation without error."""
    filters = {
        "view_count": {"gt": 1000},
        "title": {"contains": "test"},
        "keywords": {"contains_any": ["a", "b"]},
        "publish_date": {"eq": date(2023, 1, 1)},
        "is_hearted": {"eq": True},
    }
    try:
        validate_filters(filters)
    except (ValueError, TypeError) as e:
        pytest.fail(f"Valid filters raised an unexpected exception: {e}")
