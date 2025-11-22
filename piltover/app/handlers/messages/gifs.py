from datetime import datetime, UTC

from tortoise.expressions import Q

import piltover.app.utils.updates_manager as upd
from piltover.app.utils.utils import telegram_hash
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.models import User, SavedGif, File
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl.functions.messages import SaveGif, GetSavedGifs
from piltover.tl.types.messages import SavedGifs, SavedGifsNotModified
from piltover.worker import MessageHandler

handler = MessageHandler("messages.gifs")


@handler.on_request(SaveGif, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def save_gif(request: SaveGif, user: User) -> bool:
    valid, const = File.is_file_ref_valid(request.id.file_reference, user.id, request.id.id)
    if not valid:
        raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID", reason="file_reference is invalid")
    file_q = Q(id=request.id.id)
    if const:
        file_q &= Q(constant_access_hash=request.id.access_hash, constant_file_ref=request.id.file_reference[12:])
    else:
        ctx = request_ctx.get()
        if not File.check_access_hash(user.id, ctx.auth_id, request.id.id, request.id.access_hash):
            raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID", reason="access_hash is invalid")
    file = await File.get_or_none(file_q)

    await SavedGif.update_or_create(user=user, file=file, defaults={
        "last_access": datetime.now(UTC)
    })

    await upd.update_saved_gifs(user)
    return True


@handler.on_request(GetSavedGifs, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_saved_gifs(request: GetSavedGifs, user: User) -> SavedGifs | SavedGifsNotModified:
    query = SavedGif.filter(user=user).order_by("-last_access").limit(AppConfig.SAVED_GIFS_LIMIT).select_related("gif")
    ids = await query.values_list("id", flat=True)

    gifs_hash = telegram_hash(ids, 64)
    if gifs_hash and request.hash and gifs_hash == request.hash:
        return SavedGifsNotModified()

    return SavedGifs(
        hash=gifs_hash,
        gifs=[
            gif.gif.to_tl_document()
            for gif in await query
        ]
    )
