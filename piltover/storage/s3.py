from uuid import UUID

from s3lite import Client

from .base import BaseStorage, BaseStorageComponent, StorageType, StorageBuffer
from ..tl.base.internal import UploadPartState, UploadState
from ..tl.types.internal import UploadStateS3, UploadPartStateS3


class S3FileStorageComponent(BaseStorageComponent):
    def __init__(self, client: Client, component_name: str) -> None:
        self._client = client
        self._bucket = component_name

    async def get_part(
            self, file_id: UUID, offset: int, length: int, suffix: str | None = None,
    ) -> bytes | None:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"

        # TODO: handle 404
        obj = await self._client.download_object(self._bucket, file_name, in_memory=True, offset=offset, limit=length)
        return obj.read()

    async def get_location(self, file_id: UUID, suffix: str | None = None) -> str:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"

        return self._client.share(self._bucket, file_name, ttl=60)


class S3FileStorageDocuments(S3FileStorageComponent):
    NAME = "documents"

    def __init__(self, client: Client) -> None:
        super().__init__(client, self.NAME)


class S3FileStoragePhotos(S3FileStorageComponent):
    NAME = "photos"

    def __init__(self, client: Client) -> None:
        super().__init__(client, self.NAME)


class S3FileStorage(BaseStorage):
    def __init__(self, endpoint: str, access_key_id: str, access_key_secret: str) -> None:
        self._client = Client(access_key_id, access_key_secret, endpoint)
        self._documents = S3FileStorageDocuments(self._client)
        self._photos = S3FileStoragePhotos(self._client)

    async def init_upload(self, file_id: UUID, suffix: str | None = None) -> UploadState:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"

        upload_id = await self._client.create_multipart_upload("uploading", file_name)
        return UploadStateS3(upload_id=upload_id)

    async def save_part(
            self, file_id: UUID, part_id: int, data: StorageBuffer, state: UploadState | None,
            suffix: str | None = None,
    ) -> UploadPartState:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"

        etag = await self._client.upload_object_part("uploading", file_name, state.upload_id, part_id + 1, data)
        return UploadPartStateS3(part_id=part_id + 1, etag=etag)

    async def finalize_upload_as(
            self, file_id: UUID, as_: StorageType, parts: list[UploadPartState], state: UploadState | None,
            suffix: str | None = None,
    ) -> None:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"

        # TODO: finalize multipart upload
        # TODO: copy object to specific bucket
        # TODO: remove object from "uploading" bucket
        ...

    @property
    def documents(self) -> BaseStorageComponent:
        return self._documents

    @property
    def photos(self) -> BaseStorageComponent:
        return self._photos
