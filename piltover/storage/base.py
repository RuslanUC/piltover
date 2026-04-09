from abc import ABC, abstractmethod
from enum import StrEnum
from uuid import UUID

from piltover.tl.base.internal import UploadState, UploadPartState


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
    async def init_upload(self, file_id: UUID, suffix: str | None = None) -> UploadState | None:
        ...

    @abstractmethod
    async def save_part(
            self, file_id: UUID, part_id: int, data: StorageBuffer, is_last: bool, state: UploadState | None,
            suffix: str | None = None,
    ) -> UploadPartState:
        ...

    @abstractmethod
    async def finalize_upload_as(
            self, file_id: UUID, as_: StorageType, parts: list[UploadPartState], state: UploadState | None,
            suffix: str | None = None,
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
