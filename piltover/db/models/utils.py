from __future__ import annotations

from enum import IntFlag
from typing import Any, TypeVar, cast

import tortoise
from pypika_tortoise import SqlContext, Dialects
from pypika_tortoise.terms import Function as PypikaFunction
from pypika_tortoise.utils import format_alias_sql
from tortoise.expressions import Function

IntFlagT = TypeVar("IntFlagT", bound=IntFlag)


class IntFlagFieldInstance(tortoise.fields.BigIntField):
    def __init__(self, enum_type: type[IntFlag], **kwargs: Any) -> None:
        for item in enum_type:
            try:
                int(cast(int | str, item.value))
            except ValueError:
                raise tortoise.ConfigurationError("IntFlagField only supports integer enums!")

        if "description" not in kwargs:
            kwargs["description"] = "\n".join([f"{e.name}: {e.value}" for e in enum_type])[:2048]

        super().__init__(**kwargs)
        self.enum_type = enum_type

    def to_python_value(self, value: int | None) -> IntFlag | None:
        value = self.enum_type(value) if value is not None else None
        return value

    def to_db_value(self, value: IntFlag | int | None, instance: type[tortoise.Model] | tortoise.Model) -> int | None:
        if isinstance(value, IntFlag):
            value = int(value)
        if isinstance(value, int):
            value = int(self.enum_type(value))
        self.validate(value)
        return value


def IntFlagField(enum_type: type[IntFlagT], **kwargs: Any) -> IntFlagT:
    return IntFlagFieldInstance(enum_type, **kwargs)  # type: ignore


class DatetimeToUnixPika(PypikaFunction):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(kwargs.get("alias"))
        self.args: list = [self.wrap_constant(param) for param in args]

    def get_function_sql(self, ctx: SqlContext) -> str:
        args = ",".join(self.get_arg_sql(arg, ctx) for arg in self.args)

        if ctx.dialect is Dialects.MYSQL:
            return f"UNIX_TIMESTAMP({args})"
        elif ctx.dialect is Dialects.SQLITE:
            return f"CAST(strftime('%s', {args}) AS INT)"
        elif ctx.dialect is Dialects.POSTGRESQL:
            return f"DATE_PART('epoch', {args})"
        elif ctx.dialect is Dialects.MSSQL:
            return f"DATEDIFF(SECOND, '1970-01-01', {args})"

        raise RuntimeError(f"Dialect {ctx.dialect!r} is not supported!")

    def get_sql(self, ctx: SqlContext) -> str:
        function_sql = self.get_function_sql(ctx)

        if ctx.with_alias:
            return format_alias_sql(function_sql, self.alias, ctx)

        return function_sql


class DatetimeToUnix(Function):
    database_func = DatetimeToUnixPika

    @staticmethod
    def is_supported(dialect: str) -> bool:
        return dialect in ("mysql", "sqlite", "postgres", "postgresql", "mssql")
