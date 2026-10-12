from datetime import date, datetime

NUMERIC_OPERATORS = {"gt", "gte", "lt", "lte", "eq"}
# Date filters additionally accept the readable aliases after/before
# (== gt/lt). _check_date_condition has always handled them; M22 brings
# the schema into agreement so validate_filters accepts them too.
DATE_OPERATORS = NUMERIC_OPERATORS | {"after", "before"}
TEXT_OPERATORS = {"contains", "re", "eq"}
LIST_OPERATORS = {"contains_any", "contains_all"}
BOOL_OPERATORS = {"eq"}

FILTER_SCHEMA = {
    # Video/Shorts Filters
    "view_count": {
        "type": int,
        "operators": NUMERIC_OPERATORS,
        "schema_type": "numerical",
    },
    "duration_seconds": {
        "type": int,
        "operators": NUMERIC_OPERATORS,
        "schema_type": "numerical",
    },
    "like_count": {
        "type": int,
        "operators": NUMERIC_OPERATORS,
        "schema_type": "numerical",
    },
    "title": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    # description_snippet was removed in 0.8.0 (C1): only the retired
    # videoRenderer shape emitted it, so the filter silently dropped
    # every video on current pages. full_description replaces it.
    "full_description": {
        "type": str,
        "operators": TEXT_OPERATORS,
        "schema_type": "text",
    },
    "category": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    "keywords": {"type": list, "operators": LIST_OPERATORS, "schema_type": "list"},
    "publish_date": {
        "type": (str, date, datetime),
        "operators": DATE_OPERATORS,
        "schema_type": "date",
    },
    # Comment Filters
    "reply_count": {
        "type": int,
        "operators": NUMERIC_OPERATORS,
        "schema_type": "numerical",
    },
    "author": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    "text": {"type": str, "operators": TEXT_OPERATORS, "schema_type": "text"},
    # C1 (0.8.0): renamed to match the keys the comment parser actually
    # emits. The old spellings (channel_id, is_hearted_by_owner,
    # is_by_owner) never matched a real comment and now fail validation
    # loudly instead of silently dropping everything.
    "author_channel_id": {
        "type": str,
        "operators": TEXT_OPERATORS,
        "schema_type": "text",
    },
    "is_reply": {"type": bool, "operators": BOOL_OPERATORS, "schema_type": "bool"},
    "is_hearted": {"type": bool, "operators": BOOL_OPERATORS, "schema_type": "bool"},
    "is_creator": {"type": bool, "operators": BOOL_OPERATORS, "schema_type": "bool"},
    "is_pinned": {"type": bool, "operators": BOOL_OPERATORS, "schema_type": "bool"},
}


# Which record each field exists on. A comment key on a video filter (or
# the reverse) can never match: on videos it was routed to the slow path,
# fetching full metadata for every video to return nothing; on comments
# it was ignored. publish_date and like_count exist on both.
VIDEO_FILTER_FIELDS = frozenset(
    {
        "view_count",
        "duration_seconds",
        "like_count",
        "title",
        "full_description",
        "category",
        "keywords",
        "publish_date",
    }
)
COMMENT_FILTER_FIELDS = frozenset(
    {
        "text",
        "author",
        "author_channel_id",
        "like_count",
        "reply_count",
        "publish_date",
        "is_reply",
        "is_hearted",
        "is_creator",
        "is_pinned",
    }
)
_FIELDS_BY_KIND = {"video": VIDEO_FILTER_FIELDS, "comment": COMMENT_FILTER_FIELDS}

# Accepted value types per schema_type. Checked by FIELD, not operator:
# "eq" is shared by text, numeric and bool, so an operator-based check let
# {"title": {"eq": 5}} through (AttributeError later) and
# {"view_count": {"eq": "100"}} through (silently matched nothing).
_VALUE_TYPES = {
    "numerical": (int, float),
    "text": (str,),
    "list": (list,),
    "bool": (bool,),
    "date": (str, date, datetime),
}


# Tombstones for keys that existed before 0.8.0. A key with history must
# not fail like a typo — the error carries the migration, so users don't
# need the CHANGELOG to fix their call.
_RETIRED_FILTERS = {
    "description_snippet": (
        "removed in 0.8.0 — YouTube listings no longer carry description "
        "text, so it silently matched nothing. Use 'full_description' "
        "(slow: one request per scanned video; bound the scan with "
        "start_date or max_videos)"
    ),
    "channel_id": "renamed to 'author_channel_id' in 0.8.0",
    "is_by_owner": "renamed to 'is_creator' in 0.8.0",
    "is_hearted_by_owner": "renamed to 'is_hearted' in 0.8.0",
}


def validate_filters(filters: dict, kind: str | None = None):
    """
    Validates a filter dictionary against the defined FILTER_SCHEMA.

    Args:
        filters: The filter dictionary.
        kind: "video" or "comment" to also reject fields that don't exist
            on that kind of record. None checks the schema only.

    Raises:
        ValueError: If a filter field or operator is invalid, or the field
            doesn't apply to ``kind``. Retired pre-0.8.0 keys raise with
            migration guidance instead of a plain unknown-field error.
        TypeError: If a filter value has an incorrect type for its field.
    """
    if not filters:
        return

    for field, conditions in filters.items():
        if field in _RETIRED_FILTERS:
            raise ValueError(
                f"Filter field '{field}' was {_RETIRED_FILTERS[field]}."
            )
        if field not in FILTER_SCHEMA:
            raise ValueError(f"Unknown filter field: '{field}'")

        if kind is not None and field not in _FIELDS_BY_KIND[kind]:
            raise ValueError(
                f"Filter field '{field}' does not apply to {kind}s. "
                f"Valid {kind} fields: {sorted(_FIELDS_BY_KIND[kind])}"
            )

        schema = FILTER_SCHEMA[field]
        valid_operators = schema["operators"]
        allowed_types = _VALUE_TYPES[schema["schema_type"]]

        if not isinstance(conditions, dict):
            raise TypeError(f"Filter for '{field}' must be a dictionary.")

        for op, value in conditions.items():
            if op not in valid_operators:
                raise ValueError(f"Invalid operator '{op}' for field '{field}'")

            # bool is an int subclass; True is not a view count.
            value_type_valid = isinstance(value, allowed_types) and not (
                schema["schema_type"] == "numerical" and isinstance(value, bool)
            )
            if not value_type_valid:
                raise TypeError(
                    f"Invalid value type for '{field}' filter. "
                    f"Expected {schema['type']}, got {type(value)}"
                )
