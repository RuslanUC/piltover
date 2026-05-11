from collections.abc import Collection
from typing import overload, TypeVar, NoReturn, Iterator, Generic, Any, Sequence

_T_co = TypeVar("_T_co", covariant=True)


class RepeatedListIterator(Iterator[_T_co], Generic[_T_co]):
    __slots__ = ("_collection", "_repeat_times", "_pos")

    def __init__(self, collection: Sequence[_T_co], repeat_times: int) -> None:
        self._collection = collection
        self._repeat_times = repeat_times
        self._pos = 0

    def __next__(self) -> _T_co:
        if self._pos >= len(self._collection) * self._repeat_times:
            raise StopIteration
        pos = self._pos
        self._pos += 1
        return self._collection[pos % len(self._collection)]


class RepeatedList(Collection[_T_co], Generic[_T_co]):
    __slots__ = ("_collection", "_repeat_times",)

    def __init__(self, collection: Sequence[_T_co], repeat_times: int = 1) -> None:
        self._collection = collection
        self._repeat_times = repeat_times

    @overload
    def __getitem__(self, index: int) -> _T_co: ...

    @overload
    def __getitem__(self, index: slice) -> NoReturn: ...

    def __getitem__(self, index: int | slice) -> _T_co:
        if isinstance(index, slice) or index < 0:
            raise NotImplementedError
        if index >= len(self):
            raise IndexError
        return self._collection[index % len(self._collection)]

    def __len__(self) -> int:
        return len(self._collection) * self._repeat_times

    def __iter__(self) -> Iterator[_T_co]:
        return RepeatedListIterator(self._collection, self._repeat_times)

    def __contains__(self, x: Any, /) -> bool:
        return x in self._collection
