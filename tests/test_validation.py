import pytest
from datetime import date

from yt_meta.validators import validate_filters


def test_validate_filters_invalid_field():
    """Test that an unknown filter field raises a ValueError."""
    filters = {"non_existent_field": {"eq": 1}}
    with pytest.raises(ValueError, match="Unknown filter field"):
        validate_filters(filters)


def test_validate_filters_invalid_operator():
    """Test that an invalid operator for a known field raises a ValueError."""
    # Numerical field with a text operator
    filters = {"view_count": {"contains": "text"}}
    with pytest.raises(ValueError, match="Invalid operator 'contains' for field 'view_count'"):
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
        "is_hearted_by_owner": {"eq": True},
    }
    try:
        validate_filters(filters)
    except (ValueError, TypeError) as e:
        pytest.fail(f"Valid filters raised an unexpected exception: {e}") 