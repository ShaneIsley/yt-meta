from datetime import date, datetime

NUMERIC_OPERATORS = {"gt", "gte", "lt", "lte", "eq"}
TEXT_OPERATORS = {"contains", "re", "eq"}
LIST_OPERATORS = {"contains_any", "contains_all"}
BOOL_OPERATORS = {"eq"}

FILTER_SCHEMA = {
    # Video/Shorts Filters
    "view_count":          {"type": int, "operators": NUMERIC_OPERATORS},
    "duration_seconds":    {"type": int, "operators": NUMERIC_OPERATORS},
    "like_count":          {"type": int, "operators": NUMERIC_OPERATORS},
    "title":               {"type": str, "operators": TEXT_OPERATORS},
    "description_snippet": {"type": str, "operators": TEXT_OPERATORS},
    "full_description":    {"type": str, "operators": TEXT_OPERATORS},
    "category":            {"type": str, "operators": TEXT_OPERATORS},
    "keywords":            {"type": list, "operators": LIST_OPERATORS},
    "publish_date":        {"type": (str, date, datetime), "operators": NUMERIC_OPERATORS},

    # Comment Filters
    "reply_count":         {"type": int, "operators": NUMERIC_OPERATORS},
    "author":              {"type": str, "operators": TEXT_OPERATORS},
    "text":                {"type": str, "operators": TEXT_OPERATORS},
    "channel_id":          {"type": str, "operators": TEXT_OPERATORS},
    "is_reply":            {"type": bool, "operators": BOOL_OPERATORS},
    "is_hearted_by_owner": {"type": bool, "operators": BOOL_OPERATORS},
    "is_by_owner":         {"type": bool, "operators": BOOL_OPERATORS},
}


def validate_filters(filters: dict):
    """
    Validates a filter dictionary against the defined FILTER_SCHEMA.

    Raises:
        ValueError: If a filter field or operator is invalid.
        TypeError: If a filter value has an incorrect type.
    """
    if not filters:
        return

    for field, condition in filters.items():
        if field not in FILTER_SCHEMA:
            raise ValueError(f"Unknown filter field: '{field}'")

        schema = FILTER_SCHEMA[field]
        expected_type = schema["type"]
        valid_operators = schema["operators"]

        if not isinstance(condition, dict):
            raise TypeError(f"Condition for '{field}' must be a dictionary.")

        for op, value in condition.items():
            if op not in valid_operators:
                raise ValueError(f"Invalid operator '{op}' for field '{field}'")

            # Type check the value
            value_type_valid = False
            if field == "publish_date":
                if isinstance(value, (str, date, datetime)):
                    value_type_valid = True
            elif op in TEXT_OPERATORS and isinstance(value, str):
                value_type_valid = True
            elif op in NUMERIC_OPERATORS and isinstance(value, (int, float)):
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