from abc import abstractmethod, ABC
from typing import TypeVar

from piltover.tl import TLObject

T = TypeVar("T", bound=TLObject)

class BaseUpgrader(ABC):
    BASE_TYPE: type[T]
    BASE_LAYER: int

    @classmethod
    @abstractmethod
    def upgrade(cls, from_obj: T) -> TLObject:  # pragma: no cover
        ...


class BaseDowngrader(ABC):
    BASE_TYPE: type[T]
    TARGET_LAYER: int

    @classmethod
    @abstractmethod
    def downgrade(cls, from_obj: T) -> TLObject:   # pragma: no cover
        ...


class AutoDowngrader(BaseDowngrader):
    TARGET_TYPE: type[TLObject]
    REMOVE_FIELDS: set[str]

    @classmethod
    def downgrade(cls, from_obj: T) -> TLObject:
        kwargs = {k: v for k, v in from_obj.to_dict().items() if k not in cls.REMOVE_FIELDS}

        return cls.TARGET_TYPE(**kwargs)
