from __future__ import annotations

from io import BytesIO
from time import time
from typing import TYPE_CHECKING

from piltover.context import serialization_ctx

if TYPE_CHECKING:
    from piltover.tl import types

    FileTypes = types.InputPhoto | types.InputEncryptedFileLocation | types.InputDocumentFileLocation \
                | types.InputSecureFileLocation | types.InputPhotoFileLocation | types.Photo | types.EncryptedFile \
                | types.EncryptedFile_133 | types.Document | types.Document_133
    FileTypesRef = types.InputPhoto | types.InputDocumentFileLocation | types.InputPhotoFileLocation | types.Photo \
                   | types.Document | types.Document_133


def file_fill_access_hash_calc(obj: FileTypes) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    from piltover.db.models import File
    return File.make_access_hash(ctx.user_id, ctx.auth_id, obj.id)


def file_fill_file_reference_calc(obj: FileTypesRef) -> bytes:
    from piltover.tl.types.internal_access import FileReferencePayload

    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.file_reference

    payload = FileReferencePayload.read(BytesIO(obj.file_reference))
    created_at = payload.created_at if payload.created_at else int(time())

    from piltover.db.models import File
    return File.make_file_reference(ctx.user_id, payload.file_id, created_at)
