"""Regression tests for SQLAlchemy model column defaults.

The bug these guard against: a timestamp column declared with
``default=get_current_utc_time()`` (called) instead of
``default=get_current_utc_time`` (the callable). A called default is
evaluated once at import time and frozen, so every row gets the same
process-start timestamp. A callable default is invoked per-insert.
"""

from app.models import (
    App,
    Category,
    Config,
    Memory,
    MemoryStatusHistory,
    User,
)

# (model, column_name) pairs that must use a per-insert callable default.
_CALLABLE_DEFAULT_COLUMNS = [
    (User, "created_at"),
    (User, "updated_at"),
    (App, "created_at"),
    (App, "updated_at"),
    (Config, "created_at"),
    (Config, "updated_at"),
    (Memory, "created_at"),
    (Memory, "updated_at"),
    (Category, "created_at"),  # the regression: was a frozen import-time value
    (Category, "updated_at"),
    (MemoryStatusHistory, "changed_at"),
]


def test_timestamp_defaults_are_callable_not_frozen():
    for model, column_name in _CALLABLE_DEFAULT_COLUMNS:
        column = model.__table__.c[column_name]
        default = column.default
        assert default is not None, f"{model.__name__}.{column_name} has no default"
        assert default.is_callable, (
            f"{model.__name__}.{column_name} default is a frozen scalar "
            f"(evaluated once at import) — it must be the callable "
            f"get_current_utc_time, not a called value"
        )


def test_category_created_at_is_not_a_frozen_scalar():
    # Pin the specific column that regressed. The bug made this a scalar
    # default (a single datetime captured at import time); the fix makes it a
    # per-insert callable. SQLAlchemy wraps the callable, so assert on the
    # default *kind* rather than function identity.
    import datetime

    default = Category.__table__.c["created_at"].default
    assert default.is_callable, "Category.created_at must be a callable default"
    assert not default.is_scalar, "Category.created_at must not be a frozen scalar"
    assert not isinstance(default.arg, datetime.datetime)
