from pathlib import Path
from typing import AsyncGenerator, cast

from loguru import logger
from pyrogram import Client, StopTransmission
from pyrogram.client import log
from pyrogram.file_id import ThumbnailSource, FileType, FileId
from pyrogram.raw.functions.auth import ExportAuthorization, ImportAuthorization
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import Document, PhotoSize, PhotoPathSize, InputDocumentFileLocation, InputPhotoFileLocation
from pyrogram.raw.types.upload import File, FileCdnRedirect
from pyrogram.session import Session, Auth


class ClientCachedMediaSessions(Client):
    async def get_file(
        self,
        file_id: FileId,
        file_size: int = 0,
        limit: int = 0,
        offset: int = 0,
        progress: ... = None,
        progress_args: ... = (),
    ) -> AsyncGenerator[bytes, None] | None:
        file_type = file_id.file_type

        if file_type == FileType.CHAT_PHOTO:
            raise RuntimeError("Chat photos are not supported!")
        elif file_type == FileType.PHOTO:
            location = InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size
            )
        else:
            location = InputDocumentFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size
            )

        current = 0
        total = abs(limit) or (1 << 31) - 1
        chunk_size = 1024 * 1024
        offset_bytes = abs(offset) * chunk_size

        dc_id = file_id.dc_id

        async with self.media_sessions_lock:
            need_session_init = False
            if dc_id not in self.media_sessions:
                need_session_init = True
                self.media_sessions[dc_id] = Session(
                    self, dc_id,
                    await Auth(self, dc_id, await self.storage.test_mode()).create()
                    if dc_id != await self.storage.dc_id()
                    else await self.storage.auth_key(),
                    await self.storage.test_mode(),
                    is_media=True
                )

            session = self.media_sessions[dc_id]

            try:
                if need_session_init:
                    await session.start()
                    if dc_id != await self.storage.dc_id():
                        exported_auth = await self.invoke(ExportAuthorization(dc_id=dc_id))
                        await session.invoke(ImportAuthorization(id=exported_auth.id, bytes=exported_auth.bytes))

                r = await session.invoke(
                    GetFile(
                        location=location,
                        offset=offset_bytes,
                        limit=chunk_size,
                        cdn_supported=False,
                    ),
                    sleep_threshold=30
                )

                if isinstance(r, File):
                    while True:
                        chunk = cast(bytes, r.bytes)

                        yield chunk

                        current += 1
                        offset_bytes += chunk_size

                        if len(chunk) < chunk_size or current >= total:
                            break

                        r = await session.invoke(
                            GetFile(
                                location=location,
                                offset=offset_bytes,
                                limit=chunk_size
                            ),
                            sleep_threshold=30
                        )

                elif isinstance(r, FileCdnRedirect):
                    raise RuntimeError("Cdn are not supported")
            except StopTransmission:
                raise
            except Exception as e:
                log.exception(e)
            #finally:
            #    await session.stop()


def doc_to_fileid(doc: Document, thumb: PhotoSize | None = None) -> FileId:
    return FileId(
        major=FileId.MAJOR,
        minor=FileId.MINOR,
        file_type=FileType.DOCUMENT if thumb is None else FileType.THUMBNAIL,
        dc_id=doc.dc_id,
        file_reference=doc.file_reference,
        media_id=doc.id,
        access_hash=doc.access_hash,

        thumbnail_source=None if thumb is None else ThumbnailSource.THUMBNAIL,
        thumbnail_file_type=None if thumb is None else FileType.STICKER,
        thumbnail_size="" if thumb is None else thumb.type,
    )


async def download_document(client: Client, idx: int, doc: Document, out_dir: Path) -> None:
    await client.handle_download(
        (
            doc_to_fileid(doc),
            out_dir / "files",
            f"{doc.id}-{idx}.{doc.mime_type.split('/')[-1]}",
            False,
            doc.size,
            None,
            (),
        )
    )

    for thumb in doc.thumbs:
        if isinstance(thumb, PhotoPathSize):
            with open(out_dir / f"files/{doc.id}-{idx}-thumb-{thumb.type}.bin", "wb") as f:
                f.write(thumb.bytes)
        elif isinstance(thumb, PhotoSize):
            await client.handle_download(
                (
                    doc_to_fileid(doc, thumb),
                    out_dir / "files",
                    f"{doc.id}-{idx}-thumb-{thumb.type}.{doc.mime_type.split('/')[-1]}",
                    False,
                    doc.size,
                    None,
                    (),
                )
            )
        else:
            logger.warning(f"Unknown thumb type: {thumb}")
