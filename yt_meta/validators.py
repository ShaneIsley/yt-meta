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


def validate_filters(filters: dict):
    """
    Validates a filter dictionary against the defined FILTER_SCHEMA.

    Raises:
        ValueError: If a filter field or operator is invalid. Retired
            pre-0.8.0 keys raise with migration guidance instead of a
            plain unknown-field error.
        TypeError: If a filter value has an incorrect type.
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

        schema = FILTER_SCHEMA[field]
        valid_operators = schema["operators"]

        if not isinstance(conditions, dict):
            raise TypeError(f"Filter for '{field}' must be a dictionary.")

        for op, value in conditions.items():
            if op not in valid_operators:
                raise ValueError(f"Invalid operator '{op}' for field '{field}'")

            # Type check the value
            value_type_valid = False
            if field == "publish_date":
                if isinstance(value, str | date | datetime):
                    value_type_valid = True
            elif op in TEXT_OPERATORS and isinstance(value, str):
                value_type_valid = True
            elif op in NUMERIC_OPERATORS and isinstance(value, int | float):
                value_type_valid = True
            elif op in LIST_OPERATORS and isinstance(value, list):
                value_type_valid = True
            elif op in BOOL_OPERATORS and isinstance(value, bool):
                value_type_valid = True

            if not value_type_valid:
                raise TypeError(
                    f"Invalid value type for '{field}' filter. "
                    f"Expected {schema['type']}, got {type(value)}"
                )
