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


def test_removed_and_renamed_filter_keys_raise_with_migration_guidance():
    """Tombstone errors: a key that used to exist must not fail like a
    typo. The error names what happened (removed/renamed in 0.8.0) and
    the replacement, so users don't need the CHANGELOG to migrate."""
    cases = {
        "description_snippet": "full_description",
        "channel_id": "author_channel_id",
        "is_by_owner": "is_creator",
        "is_hearted_by_owner": "is_hearted",
    }
    for old_key, replacement in cases.items():
        with pytest.raises(ValueError, match=replacement):
            validate_filters({old_key: {"eq": "x"}})
        with pytest.raises(ValueError, match="0.8.0"):
            validate_filters({old_key: {"eq": "x"}})


def test_genuinely_unknown_filter_key_still_reads_as_unknown():
    """A key with no history keeps the plain unknown-field error."""
    with pytest.raises(ValueError, match="Unknown filter field"):
        validate_filters({"view_cont": {"gt": 1}})


@pytest.mark.parametrize(
    ("filters", "exc"),
    [
        ({"title": {"eq": 5}}, TypeError),
        ({"view_count": {"eq": "100"}}, TypeError),
        ({"view_count": {"gt": True}}, TypeError),
        ({"is_pinned": {"eq": 1}}, TypeError),
        ({"keywords": {"contains_any": "python"}}, TypeError),
    ],
)
def test_value_type_is_checked_per_field(filters, exc):
    """REGRESSION (2026-10 review): values were type-checked by operator,
    and "eq" is shared by text, numeric and bool fields. A title compared
    to 5 crashed later with AttributeError; a view_count compared to "100"
    silently matched nothing."""
    with pytest.raises(exc):
        validate_filters(filters)


def test_comment_field_rejected_on_video_filters():
    """REGRESSION (2026-10 review): "text" on a video filter was routed to
    the slow path, hydrating every video to return nothing."""
    with pytest.raises(ValueError, match="does not apply to videos"):
        validate_filters({"text": {"contains": "x"}}, kind="video")


def test_video_field_rejected_on_comment_filters():
    """REGRESSION (2026-10 review): "title" on a comment filter was
    silently ignored."""
    with pytest.raises(ValueError, match="does not apply to comments"):
        validate_filters({"title": {"contains": "x"}}, kind="comment")


def test_shared_fields_accepted_for_both_kinds():
    shared = {"like_count": {"gte": 10}, "publish_date": {"after": "2024-01-01"}}
    validate_filters(shared, kind="video")
    validate_filters(shared, kind="comment")


def test_field_families_match_the_filter_pipeline():
    """The validator's per-kind field sets must agree with the sets the
    filtering pipeline routes on, and together cover the schema."""
    from yt_meta.filtering import (
        COMMENT_FILTER_KEYS,
        FAST_VIDEO_FILTERS,
        SLOW_FILTER_KEYS,
    )
    from yt_meta.validators import (
        COMMENT_FILTER_FIELDS,
        FILTER_SCHEMA,
        VIDEO_FILTER_FIELDS,
    )

    assert VIDEO_FILTER_FIELDS == FAST_VIDEO_FILTERS | SLOW_FILTER_KEYS
    assert COMMENT_FILTER_FIELDS == COMMENT_FILTER_KEYS
    assert VIDEO_FILTER_FIELDS | COMMENT_FILTER_FIELDS == set(FILTER_SCHEMA)
