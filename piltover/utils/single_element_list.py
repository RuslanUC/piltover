from collections.abc import Sequence, Collection
from typing import overload, TypeVar, NoReturn, Iterable, Iterator, Generic, Any

_T_co = TypeVar("_T_co", covariant=True)


class SingleElementListIterator(Iterator[_T_co], Generic[_T_co]):
    __slots__ = ("_item", "_iters_left",)

    def __init__(self, item: _T_co, iters_left: int) -> None:
        self._item = item
        self._iters_left = iters_left

    def __next__(self) -> _T_co:
        if self._iters_left <= 0:
            raise StopIteration
        self._iters_left -= 1
        return self._item


class SingleElementList(Collection[_T_co], Generic[_T_co]):
    __slots__ = ("_item", "_len",)

    def __init__(self, item: _T_co, length: int = 1) -> None:
        self._item = item
        self._len = length

    @overload
    def __getitem__(self, index: int) -> _T_co: ...

    @overload
    def __getitem__(self, index: slice) -> NoReturn: ...

    def __getitem__(self, index: int | slice) -> _T_co:
        if isinstance(index, slice):
            raise NotImplementedError
        if index >= self._len:
            raise IndexError
        return self._item

    def __len__(self) -> int:
        return self._len

    def __iter__(self) -> Iterator[_T_co]:
        return SingleElementListIterator(self._item, self._len)

    def __contains__(self, x: Any, /) -> bool:
        return self._item == x
