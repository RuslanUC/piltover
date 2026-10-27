from collections.abc import Iterator, Sequence
from typing import overload, NoReturn, Any


class SingleElementListIterator[T](Iterator[T]):
    __slots__ = ("_item", "_iters_left",)

    def __init__(self, item: T, iters_left: int) -> None:
        self._item = item
        self._iters_left = iters_left

    def __next__(self) -> T:
        if self._iters_left <= 0:
            raise StopIteration
        self._iters_left -= 1
        return self._item


class SingleElementList[T](Sequence[T]):
    __slots__ = ("_item", "_len",)

    def __init__(self, item: T, length: int = 1) -> None:
        self._item = item
        self._len = length

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> NoReturn: ...

    def __getitem__(self, index: int | slice) -> T:
        if isinstance(index, slice):
            raise NotImplementedError
        if index >= self._len:
            raise IndexError
        return self._item

    def __len__(self) -> int:
        return self._len

    def __iter__(self) -> Iterator[T]:
        return SingleElementListIterator(self._item, self._len)

    def __contains__(self, x: Any, /) -> bool:
        return self._item == x
