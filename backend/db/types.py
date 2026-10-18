"""Column types shared by the models."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint, Text
from sqlalchemy.types import TypeDecorator


class TextEnum(TypeDecorator):
    """A `StrEnum` stored as plain text, read back as the enum.

    The allowed values are enforced by a CHECK constraint (`enum_check`) rather than
    a PostgreSQL enum type: adding or retiring a value is then a two-line migration,
    whereas enum types are hard to change.
    """

    impl = Text
    cache_ok = True

    def __init__(self, enum: type[StrEnum]) -> None:
        super().__init__()
        self.enum = enum

    def process_bind_param(self, value, dialect):
        return None if value is None else self.enum(value).value

    def process_result_value(self, value, dialect):
        return None if value is None else self.enum(value)


def enum_check(column: str, enum: type[StrEnum]) -> CheckConstraint:
    """`<column> IN (...)` with the enum's values, named `<column>_known`."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_known")
