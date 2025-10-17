import os
from pathlib import Path
from typing import cast
from uuid import UUID

import aiofiles
import aiofiles.os
from loguru import logger

from .base import BaseStorage, BaseStorageComponent, StorageType, StorageBuffer


class LocalFileStorageComponent(BaseStorageComponent):
    def __init__(self, files_dir: Path, component_name: str) -> None:
        self._dir = files_dir / component_name
        self._dir.mkdir(parents=True, exist_ok=True)

    async def get_part(
            self, file_id: UUID, offset: int, length: int, suffix: str | None = None,
    ) -> bytes | None:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"
        file_path = self._dir / file_name

        if not file_path.exists():
            logger.warning(f"Requested file {file_path} does not exist, even tho it should")
            return None

        async with aiofiles.open(file_path, "rb") as f:
            await f.seek(offset)
            return await f.read(length)

    async def get_location(self, file_id: UUID, suffix: str | None = None) -> str:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"

        file_path = self._dir / file_name
        return str(file_path.absolute())


class LocalFileStorageDocuments(LocalFileStorageComponent):
    NAME = "documents"

    def __init__(self, files_dir: Path) -> None:
        super().__init__(files_dir, self.NAME)


class LocalFileStoragePhotos(LocalFileStorageComponent):
    NAME = "photos"

    def __init__(self, files_dir: Path) -> None:
        super().__init__(files_dir, self.NAME)


class LocalFileStorage(BaseStorage):
    def __init__(self, files_dir: Path) -> None:
        self._dir = files_dir
        self._documents = LocalFileStorageDocuments(files_dir)
        self._photos = LocalFileStoragePhotos(files_dir)

        (self._dir / "uploading").mkdir(parents=True, exist_ok=True)

    async def save_part(
            self, file_id: UUID, part_id: int, data: StorageBuffer, is_last: bool, suffix: str | None = None,
    ) -> None:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"

        if part_id > 0:
            file_name += f".part{part_id}"

        file_path = self._dir / "uploading" / file_name
        file_path.touch(exist_ok=True)

        async with aiofiles.open(file_path, "r+b") as f:
            await f.write(data)

    async def finalize_upload_as(
            self, file_id: UUID, as_: StorageType, parts_num: int, suffix: str | None = None,
    ) -> None:
        file_name = str(file_id)
        if suffix is not None:
            file_name += f"-{suffix}"

        src_path = self._dir / "uploading" / file_name
        dst_path = self._dir / cast(str, as_.value) / file_name
        logger.trace(f"Finalizing {src_path} as {as_.value}, moving to {dst_path}")

        await aiofiles.os.rename(src_path, dst_path)

        if parts_num <= 1:
            return

        async with aiofiles.open(dst_path, "r+b") as f_out:
            await f_out.seek(0, os.SEEK_END)
            for part_id in range(1, parts_num):
                append_filename = self._dir / "uploading" / f"{file_name}.part{part_id}"
                async with aiofiles.open(append_filename, "rb") as f_in:
                    await f_out.write(await f_in.read())
                await aiofiles.os.remove(append_filename)

    @property
    def documents(self) -> BaseStorageComponent:
        return self._documents

    @property
    def photos(self) -> BaseStorageComponent:
        return self._photos
