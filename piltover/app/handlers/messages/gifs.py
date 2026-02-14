from datetime import datetime, UTC

import piltover.app.utils.updates_manager as upd
from piltover.app.utils.utils import telegram_hash
from piltover.app_config import AppConfig
from piltover.db.enums import FileType
from piltover.db.models import User, SavedGif, File
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl.functions.messages import SaveGif, GetSavedGifs
from piltover.tl.types.messages import SavedGifs, SavedGifsNotModified
from piltover.worker import MessageHandler

handler = MessageHandler("messages.gifs")


@handler.on_request(SaveGif, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def save_gif(request: SaveGif, user: User) -> bool:
    doc = request.id

    if request.unsave:
        saved_gif = await SavedGif.get_or_none(user=user, gif_id=doc.id)
        if saved_gif is not None:
            await saved_gif.delete()
            await upd.update_saved_gifs(user)
        return True

    file = await File.from_input(user.id, doc.id, doc.access_hash, doc.file_reference, FileType.DOCUMENT_GIF)
    if file is None:
        raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

    await SavedGif.update_or_create(user=user, gif=file, defaults={
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
