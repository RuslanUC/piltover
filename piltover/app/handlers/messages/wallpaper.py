from io import BytesIO

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.context import request_ctx
from piltover.db.enums import MessageType, PeerType
from piltover.db.models import User, Peer, Wallpaper, ChatWallpaper, MessageRef
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, Unreachable, Error
from piltover.tl import Updates, InputPeerUser, InputUser, TLObject, MessageActionSetChatWallPaper, InputPeerChannel, \
    InputChannel
from piltover.tl.functions.messages import SetChatWallPaper
from piltover.worker import MessageHandler

handler = MessageHandler("wallpaper")


async def _get_wallpaper(request: SetChatWallPaper, user: User, peer: Peer) -> tuple[Wallpaper | None, bool]:
    create_svc_message = False

    if request.wallpaper is None and request.id is None:
        set_wallpaper = None
    elif request.wallpaper is not None:
        create_svc_message = True
        auth_id = request_ctx.get().auth_id
        set_wallpaper = await Wallpaper.from_input(request.wallpaper, user, auth_id)
        if set_wallpaper is None:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_INVALID")
    elif request.id is not None:
        message_q = MessageRef.filter(
            id=request.id, content__type=MessageType.SERVICE_CHAT_UPDATE_WALLPAPER
        ).select_related("content")
        if peer.type is PeerType.CHANNEL:
            message_q = message_q.get_or_none(peer__owner_id=None, peer__channel_id=peer.channel_id)
        else:
            message_q = message_q.get_or_none(peer=peer)
        service_message = await message_q
        if service_message is None:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_NOT_FOUND")

        try:
            action = TLObject.read(BytesIO(service_message.content.extra_info))
        except Error:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_NOT_FOUND")

        if isinstance(action, MessageActionSetChatWallPaper):
            wallpaper_id = action.wallpaper.id
        else:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_NOT_FOUND")

        set_wallpaper = await Wallpaper.get_or_none(id=wallpaper_id).select_related("document", "settings")
        if set_wallpaper is None:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_INVALID")
    else:
        raise Unreachable

    return set_wallpaper, create_svc_message


async def set_channel_wallpaper(request: SetChatWallPaper, user: User, peer: Peer) -> Updates:
    channel = peer.channel

    set_wallpaper, create_svc_message = await _get_wallpaper(request, user, peer)

    if set_wallpaper is None:
        if channel.wallpaper_id is not None:
            channel.wallpaper = None
            channel.version += 1
            await channel.save(update_fields=["wallpaper_id", "version"])
            return await upd.update_channel(channel)

        return upd.UpdatesWithDefaults(updates=[])

    channel.wallpaper = set_wallpaper
    channel.version += 1
    await channel.save(update_fields=["wallpaper_id", "version"])

    updates = await upd.update_channel(channel)
    if create_svc_message:
        # channel_peer = await Peer.get(owner=None, channel_id=peer.channel_id)
        message_updates = await send_message_internal(
            user, peer, None, None, False, author=user, type=MessageType.SERVICE_CHAT_UPDATE_WALLPAPER,
            extra_info=MessageActionSetChatWallPaper(
                same=False,
                for_both=False,
                wallpaper=set_wallpaper.to_tl(),
            ).write(),
        )
        updates.updates.extend(message_updates.updates)

    return updates


@handler.on_request(SetChatWallPaper, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def set_chat_wallpaper(request: SetChatWallPaper, user: User) -> Updates:
    if not isinstance(request.peer, (InputPeerUser, InputUser, InputPeerChannel, InputChannel)):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    peer = await Peer.from_input_peer_raise(user, request.peer)

    if peer.type is PeerType.CHANNEL:
        return await set_channel_wallpaper(request, user, peer)

    target = peer.peer_user(user)
    existing_wp = await ChatWallpaper.get_or_none(user=user, target=target).select_related("target")

    # TODO: support for_both and revert

    set_wallpaper, create_svc_message = await _get_wallpaper(request, user, peer)

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
            extra_info=MessageActionSetChatWallPaper(
                same=False,
                for_both=False,
                wallpaper=set_wallpaper.to_tl(),
            ).write(),
        )
        updates.updates.extend(message_updates.updates)

    return updates
