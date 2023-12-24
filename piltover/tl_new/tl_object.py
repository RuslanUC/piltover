from __future__ import annotations
from dataclasses import dataclass, field as dc_field, MISSING
from inspect import get_annotations
from typing import Callable, get_type_hints, get_origin, get_args

from piltover.tl_new.serialization_utils import SerializationUtils


class TLObjectBase(object):
    pass


class _BaseTLObject:
    __tl_id__: int
    __tl_name__: str
    __tl_fields__: list[TLField]
    __tl_flags__: list[TLField]


@dataclass
class TLObject(_BaseTLObject):
    @classmethod
    def tlid(cls) -> int:
        return cls.__tl_id__

    @classmethod
    def tlname(cls) -> str:
        return cls.__tl_name__

    def _calculate_flags(self, field_: TLField) -> int:
        flags = 0
        for field in self.__tl_fields__:
            if field.flag != -1 and field.flagnum == field_.flagnum:
                flags |= field.flag if getattr(self, field.name) else 0

        return flags

    def serialize(self) -> bytes:
        if not self.__tl_fields__:
            return b''
        for field in self.__tl_flags__:
            if field.is_flags:
                setattr(self, field.name, self._calculate_flags(field))

        result = b""
        flags = -1
        types = get_type_hints(self.__class__)
        for field in self.__tl_fields__:
            value = getattr(self, field.name)

            if field.is_flags:
                flags = value
            elif flags >= 0 and field.flag > 0 and not value:
                continue

            type_ = types[field.name]
            int_type = type_ if isinstance(value, int) else None
            if get_origin(type_) is list:
                int_type = get_args(type_)[0] if get_args(type_) else None
                int_type = int_type if issubclass(int_type, int) else None
            result += SerializationUtils.write(value, int_type)

        return result

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        args = {}
        flags = -1
        types = get_annotations(cls, eval_str=True)
        for field in cls.__tl_fields__:
            if field.flag != -1 and (flags & field.flag) != field.flag:
                continue

            type_ = types[field.name]
            ltype = None
            if get_origin(type_) is list:
                ltype = get_args(type_)[0] if get_args(type_) else None
                type_ = list
            value = SerializationUtils.read(stream, type_, ltype)
            args[field.name] = value
            if field.is_flags:
                flags = value

        return cls(**args)


def tl_object(id: int, name: str) -> Callable:
    def wrapper(cls: type):
        setattr(cls, "__tl_id__", id)
        setattr(cls, "__tl_name__", name)
        fields: list[TLField] = []
        flags: list[TLField] = []
        for field_name, field in cls.__dict__.items():
            if not isinstance(field, TLField):
                continue

            field.set_name(field_name)
            fields.append(field)
            if field.is_flags:
                flags.append(field)

            default = MISSING
            if field.flag != -1:
                default = False if cls.__annotations__[field_name] == "bool" else None
            if field.is_flags:
                default = 0

            setattr(cls, field_name, dc_field(kw_only=True, default=default))

        fields.sort(key=lambda field_: field_._counter)
        setattr(cls, "__tl_fields__", fields)
        setattr(cls, "__tl_flags__", flags)

        return dataclass(slots=True, order=True)(cls)

    return wrapper


@dataclass(slots=True, frozen=True)
class TLField:
    __COUNTER = 0

    is_flags: bool = False
    flag: int = -1
    flagnum: int = 1
    name: str = None
    _counter: int = dc_field(default=-1, init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, '_counter', TLField.__COUNTER)
        TLField.__COUNTER += 1

    def set_name(self, name: str) -> None:
        object.__setattr__(self, 'name', name)
