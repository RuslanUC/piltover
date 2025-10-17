from abc import ABC, abstractmethod
from enum import StrEnum
from uuid import UUID


class StorageType(StrEnum):
    PHOTO = "photos"
    DOCUMENT = "documents"


StorageBuffer = bytes | bytearray | memoryview


class BaseStorageComponent(ABC):
    @abstractmethod
    async def get_part(self, file_id: UUID, offset: int, length: int, suffix: str | None = None) -> bytes | None:
        ...

    @abstractmethod
    async def get_location(self, file_id: UUID, suffix: str | None = None) -> str:
        ...


class BaseStorage(ABC):
    @abstractmethod
    async def save_part(
            self, file_id: UUID, part_id: int, data: StorageBuffer, is_last: bool, suffix: str | None = None,
    ) -> None:
        ...

    @abstractmethod
    async def finalize_upload_as(
            self, file_id: UUID, as_: StorageType, parts_num: int, suffix: str | None = None,
    ) -> None:
        ...

    @property
    @abstractmethod
    def documents(self) -> BaseStorageComponent:
        ...

    @property
    @abstractmethod
    def photos(self) -> BaseStorageComponent:
        ...
