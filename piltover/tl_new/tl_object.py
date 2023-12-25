from __future__ import annotations
from dataclasses import dataclass, field as dc_field, MISSING
from inspect import get_annotations
from typing import Callable, get_origin, get_args, Union

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
    def __init__(self, **k):
        pass

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
        for field in self.__tl_fields__:
            value = getattr(self, field.name)

            if field.is_flags:
                flags = value
            elif flags >= 0 and field.flag > 0 and not value:
                continue

            int_type = field.type.subtype or field.type.type
            int_type = int_type if issubclass(int_type, int) else None
            result += SerializationUtils.write(value, int_type)

        return result

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        args = {}
        flags = -1
        for field in cls.__tl_fields__:
            if field.flag != -1 and (flags & field.flag) != field.flag:
                continue

            value = SerializationUtils.read(stream, field.type.type, field.type.subtype)
            args[field.name] = value
            if field.is_flags:
                flags = value

        return cls(**args)


def _resolve_annotation(annotation: type):
    origin = get_origin(annotation) or annotation
    if origin is Union:
        return _resolve_annotation(get_args(annotation)[0])
    if origin is list:
        args = get_args(annotation)
        return list, args[0]
    if origin in (int, float, bool, str, bytes) or issubclass(origin, (int, TLObject, TLObjectBase)):
        return origin, None

    raise RuntimeError(f"Unknown annotation type {annotation}!")


def tl_object(id: int, name: str) -> Callable:
    def wrapper(cls: type):
        setattr(cls, "__tl_id__", id)
        setattr(cls, "__tl_name__", name)
        fields: list[TLField] = []
        flags: list[TLField] = []
        annotations = get_annotations(cls, eval_str=True)
        for field_name, field in cls.__dict__.items():
            if not isinstance(field, TLField):
                continue

            field.name = field_name
            field.type = TLType(*_resolve_annotation(annotations[field_name]))
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


@dataclass(slots=True)
class TLType:
    type: type
    subtype: type | None


@dataclass(slots=True)
class TLField:
    __COUNTER = 0

    is_flags: bool = False
    flag: int = -1
    flagnum: int = 1
    name: str = None
    type: TLType = None
    _counter: int = dc_field(default=-1, init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, '_counter', TLField.__COUNTER)
        TLField.__COUNTER += 1
