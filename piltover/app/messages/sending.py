from collections import defaultdict
from datetime import datetime, UTC

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import upload_file, resize_photo, generate_stripped
from piltover.db.enums import MediaType, MessageType
from piltover.db.models import User, Dialog, MessageDraft, State, Peer, MessageMedia
from piltover.db.models.message import Message
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.tl import Updates, InputMediaUploadedDocument, InputMediaUploadedPhoto
from piltover.tl.functions.messages import SendMessage, DeleteMessages, EditMessage, SendMedia, SaveDraft, \
    SendMessage_148, SendMedia_148, EditMessage_136, UpdatePinnedMessage
from piltover.tl.types.messages import AffectedMessages
from piltover.utils.snowflake import Snowflake

handler = MessageHandler("messages.sending")


async def _send_message_internal(
        user: User, peer: Peer, reply_to_message_id: int | None, clear_draft: bool, author: User, **message_kwargs
) -> Updates:
    reply = await Message.get_or_none(id=reply_to_message_id, peer=peer) if reply_to_message_id else None

    peers = [peer]
    peers.extend(await peer.get_opposite())
    messages: dict[Peer, Message] = {}

    internal_id = Snowflake.make_id()
    for to_peer in peers:
        await Dialog.get_or_create(peer=to_peer)
        messages[to_peer] = await Message.create(
            internal_id=internal_id,
            peer=to_peer,
            reply_to=(await Message.get_or_none(peer=to_peer, internal_id=reply.internal_id)) if reply else None,
            author=author,
            **message_kwargs
        )

    # TODO: rewrite when pypika fixes delete with join for mysql
    # Not doing await MessageDraft.filter(...).delete()
    # Because pypika generates sql for MySql/MariaDB like "DELETE FROM `messagedraft` LEFT OUTER JOIN"
    # But `messagedraft` must also be placed between "DELETE" and "FROM", like this:
    # "DELETE `messagedraft` FROM `messagedraft` LEFT OUTER JOIN"
    if clear_draft and (draft := await MessageDraft.get_or_none(dialog__peer=peer)) is not None:
        await draft.delete()
        await UpdatesManager.update_draft(user, peer, None)

    if (upd := await UpdatesManager.send_message(user, messages, bool(message_kwargs.get("media")))) is None:
        assert False, "unknown chat type ?"

    return upd


@handler.on_request(SendMessage_148)
@handler.on_request(SendMessage)
async def send_message(request: SendMessage, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    if len(request.message) > 2000:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_TOO_LONG")

    reply_to_message_id = None
    if isinstance(request, SendMessage) and request.reply_to is not None:
        reply_to_message_id = request.reply_to.reply_to_msg_id
    elif isinstance(request, SendMessage_148) and request.reply_to_msg_id is not None:
        reply_to_message_id = request.reply_to_msg_id

    return await _send_message_internal(
        user, peer, reply_to_message_id, request.clear_draft,
        author=user, message=request.message,
    )


@handler.on_request(UpdatePinnedMessage)
async def update_pinned_message(request: UpdatePinnedMessage, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if (message := await Message.get_(request.id, peer)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    message.pinned = not request.unpin
    messages = {peer: message}

    if not request.pm_oneside:
        other_messages = await Message.filter(
            peer__user=user, internal_id=message.internal_id,
        ).select_related("peer", "author")
        for other_message in other_messages:
            other_message.pinned = message.pinned
            messages[other_message.peer] = other_message

    await Message.bulk_update(messages.values(), ["pinned"])

    result = await UpdatesManager.pin_message(user, messages)

    if not request.silent and not request.pm_oneside:
        updates = await _send_message_internal(
            user, peer, message.id, False, author=user, type=MessageType.SERVICE_PIN_MESSAGE
        )
        result.updates.extend(updates.updates)

    return result


@handler.on_request(DeleteMessages)
async def delete_messages(request: DeleteMessages, user: User):
    ids = request.id[:100]
    messages = defaultdict(list)
    for message in await Message.filter(id__in=ids, peer__owner=user).select_related("peer", "peer__user", "peer__owner"):
        messages[user].append(message.id)
        if request.revoke:
            for opposite_peer in await message.peer.get_opposite():
                opp_message = await Message.get_or_none(internal_id=message.internal_id, peer=opposite_peer)
                if opp_message is not None:
                    messages[message.peer.user].append(opp_message.id)

    all_ids = [i for ids in messages.values() for i in ids]
    if not all_ids:
        updates_state, _ = await State.get_or_create(user=user)
        return AffectedMessages(pts=updates_state.pts, pts_count=0)

    await Message.filter(id__in=all_ids).delete()
    pts = await UpdatesManager.delete_messages(user, messages)
    return AffectedMessages(pts=pts, pts_count=len(all_ids))


@handler.on_request(EditMessage_136)
@handler.on_request(EditMessage)
async def edit_message(request: EditMessage | EditMessage_136, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if (message := await Message.get_(request.id, peer)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    if message.author != user:
        raise ErrorRpc(error_code=403, error_message="MESSAGE_AUTHOR_REQUIRED")
    if message.message == request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_NOT_MODIFIED")

    peers = [peer]
    peers.extend(await peer.get_opposite())
    messages: dict[Peer, Message] = {}

    edit_date = datetime.now(UTC)
    for to_peer in peers:
        message = await Message.get_or_none(
            internal_id=message.internal_id, peer=to_peer,
        ).select_related("author", "peer")
        if message is not None:
            await message.update(message=request.message, edit_date=edit_date)
            messages[to_peer] = message

    return await UpdatesManager.edit_message(user, messages)


@handler.on_request(SendMedia_148)
@handler.on_request(SendMedia)
async def send_media(request: SendMedia | SendMedia_148, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    # TODO: InputMediaPhoto
    if not isinstance(request.media, (InputMediaUploadedDocument, InputMediaUploadedPhoto)):
        raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")
    if len(request.message) > 2000:
        raise ErrorRpc(error_code=400, error_message="MEDIA_CAPTION_TOO_LONG")

    mime = request.media.mime_type if isinstance(request.media, InputMediaUploadedDocument) else "image/jpeg"
    attributes = request.media.attributes if isinstance(request.media, InputMediaUploadedDocument) else []
    media_type = MediaType.DOCUMENT if isinstance(request.media, InputMediaUploadedDocument) else MediaType.PHOTO

    file = await upload_file(user, request.media.file, mime, attributes)
    sizes = await resize_photo(str(file.physical_id)) if mime.startswith("image/") else []
    stripped = await generate_stripped(str(file.physical_id)) if mime.startswith("image/") else b""
    await file.update(attributes=file.attributes | {"_sizes": sizes, "_size_stripped": stripped.hex()})

    media = await MessageMedia.create(file=file, spoiler=request.media.spoiler, type=media_type)

    reply_to_message_id = None
    if isinstance(request, SendMessage) and request.reply_to is not None:
        reply_to_message_id = request.reply_to.reply_to_msg_id
    elif isinstance(request, SendMessage_148) and request.reply_to_msg_id is not None:
        reply_to_message_id = request.reply_to_msg_id

    return await _send_message_internal(
        user, peer, reply_to_message_id, request.clear_draft,
        author=user, message=request.message, media=media,
    )


@handler.on_request(SaveDraft)
async def save_draft(request: SaveDraft, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    dialog = await Dialog.get_or_create(peer=peer)
    draft, _ = await MessageDraft.get_or_create(
        dialog=dialog,
        defaults={"message": request.message, "date": datetime.now()}
    )

    await UpdatesManager.update_draft(user, peer, draft)
    return True