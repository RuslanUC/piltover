from io import BytesIO

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.db.enums import MessageType
from piltover.db.models import User, Peer, Wallpaper, ChatWallpaper, Message
from piltover.exceptions import ErrorRpc, Unreachable, Error
from piltover.tl import Updates, InputPeerUser, InputUser, TLObject, MessageActionSetChatWallPaper
from piltover.tl.functions.messages import SetChatWallPaper
from piltover.tl.types.internal import MessageActionProcessSetChatWallpaper
from piltover.worker import MessageHandler

handler = MessageHandler("wallpaper")


@handler.on_request(SetChatWallPaper)
async def set_chat_wallpaper(request: SetChatWallPaper, user: User) -> Updates:
    if not isinstance(request.peer, (InputPeerUser, InputUser)):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    peer = await Peer.from_input_peer_raise(user, request.peer)

    target = peer.peer_user(user)
    existing_wp = await ChatWallpaper.get_or_none(user=user, target=target).select_related("target")

    # TODO: support for_both and revert

    create_svc_message = False

    if request.wallpaper is None and request.id is None:
        set_wallpaper = None
    elif request.wallpaper is not None:
        create_svc_message = True
        set_wallpaper = await Wallpaper.from_input(request.wallpaper)
        if set_wallpaper is None:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_INVALID")
    elif request.id is not None:
        service_message = await Message.get_or_none(
            id=request.id, peer=peer, type=MessageType.SERVICE_CHAT_UPDATE_WALLPAPER,
        )
        if service_message is None:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_NOT_FOUND")

        try:
            action = TLObject.read(BytesIO(service_message.extra_info))
        except Error:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_NOT_FOUND")

        if isinstance(action, MessageActionSetChatWallPaper):
            wallpaper_id = action.wallpaper.id
        elif isinstance(action, MessageActionProcessSetChatWallpaper):
            wallpaper_id = action.wallpaper_id
        else:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_NOT_FOUND")

        set_wallpaper = await Wallpaper.get_or_none(id=wallpaper_id).select_related("document", "settings")
        if set_wallpaper is None:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_INVALID")
    else:
        raise Unreachable

    if set_wallpaper is None:
        if existing_wp is not None:
            await existing_wp.delete()
            return await upd.update_chat_wallpaper(user, target, None)

        return upd.UpdatesWithDefaults(updates=[])

    chat_wp: ChatWallpaper

    if existing_wp is None:
        chat_wp = await ChatWallpaper.create(user=user, target=target, wallpaper=set_wallpaper)
    else:
        chat_wp = existing_wp
        chat_wp.wallpaper = set_wallpaper
        await chat_wp.save(update_fields=["wallpaper_id"])

    updates = await upd.update_chat_wallpaper(user, target, chat_wp)
    if create_svc_message:
        message_updates = await send_message_internal(
            user, peer, None, None, False, author=user, type=MessageType.SERVICE_CHAT_UPDATE_WALLPAPER,
            extra_info=MessageActionProcessSetChatWallpaper(
                same=False, for_both=False, wallpaper_id=set_wallpaper.id,
            ).write(),
        )
        updates.updates.extend(message_updates.updates)

    return updates

