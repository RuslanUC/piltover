from __future__ import annotations

from typing import TYPE_CHECKING

from piltover.context import serialization_ctx

if TYPE_CHECKING:
    from piltover.tl import types

    FileTypes = types.InputPhoto | types.InputEncryptedFileLocation | types.InputDocumentFileLocation \
                | types.InputSecureFileLocation | types.InputPhotoFileLocation | types.Photo | types.EncryptedFile \
                | types.EncryptedFile_133 | types.Document | types.Document_133


def file_fill_access_hash_calc(obj: FileTypes) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    from piltover.db.models import File
    return File.make_access_hash(ctx.user_id, ctx.auth_id, obj.id)
