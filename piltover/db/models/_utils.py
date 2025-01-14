from enum import IntFlag
from typing import Any, TypeVar

import tortoise


IntFlagT = TypeVar("IntFlagT", bound=IntFlag)


class IntFlagFieldInstance(tortoise.fields.BigIntField):
    def __init__(self, enum_type: type[IntFlag], **kwargs: Any) -> None:
        for item in enum_type:
            try:
                int(item.value)
            except ValueError:
                raise tortoise.ConfigurationError("IntFlagField only supports integer enums!")

        if "description" not in kwargs:
            kwargs["description"] = "\n".join([f"{e.name}: {int(e.value)}" for e in enum_type])[:2048]

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
