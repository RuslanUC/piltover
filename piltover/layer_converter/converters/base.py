from abc import abstractmethod, ABC
from typing import TypeVar, Generic

from piltover.tl import TLObject

TBase = TypeVar("TBase", bound=TLObject)
TTarget = TypeVar("TTarget", bound=TLObject)


class BaseDowngrader(ABC, Generic[TBase]):
    BASE_TYPE: type[TBase]
    TARGET_LAYER: int

    @classmethod
    @abstractmethod
    def downgrade(cls, from_obj: TBase) -> TLObject:   # pragma: no cover
        ...


class AutoDowngrader(BaseDowngrader[TBase], Generic[TBase, TTarget]):
    TARGET_TYPE: type[TTarget]
    REMOVE_FIELDS: set[str]

    @classmethod
    def downgrade(cls, from_obj: TBase) -> TTarget:
        # TODO: if base type is same as target type, just return from_obj
        kwargs = {k: v for k, v in from_obj.to_dict().items() if k not in cls.REMOVE_FIELDS}

        return cls.TARGET_TYPE(**kwargs)
