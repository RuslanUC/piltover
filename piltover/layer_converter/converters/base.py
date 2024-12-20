from abc import abstractmethod
from typing import TypeVar

from piltover.tl import TLObject

T = TypeVar("T", bound=TLObject)

class BaseUpgrader:
    BASE_TYPE: type[T]
    BASE_LAYER: int

    @classmethod
    @abstractmethod
    def upgrade(cls, from_obj: T) -> TLObject:  # pragma: no cover
        ...


class BaseDowngrader:
    BASE_TYPE: type[T]
    TARGET_LAYER: int

    @classmethod
    @abstractmethod
    def downgrade(cls, from_obj: T) -> TLObject:   # pragma: no cover
        ...