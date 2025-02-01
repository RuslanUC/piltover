from collections import defaultdict
from datetime import datetime, UTC

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import resize_photo, generate_stripped, validate_message_entities
from piltover.db.enums import MediaType, MessageType, PeerType
from piltover.db.models import User, Dialog, MessageDraft, State, Peer, MessageMedia, FileAccess, File, \
    Presence, UploadingFile, SavedDialog
from piltover.db.models.message import Message
from piltover.exceptions import ErrorRpc
from piltover.tl import Updates, InputMediaUploadedDocument, InputMediaUploadedPhoto, InputMediaPhoto, \
    InputMediaDocument, InputPeerEmpty
from piltover.tl.functions.messages import SendMessage, DeleteMessages, EditMessage, SendMedia, SaveDraft, \
    SendMessage_148, SendMedia_148, EditMessage_136, UpdatePinnedMessage, ForwardMessages, ForwardMessages_148
from piltover.tl.types.messages import AffectedMessages
from piltover.utils.snowflake import Snowflake
from piltover.worker import MessageHandler

handler = MessageHandler("messages.sending")

InputMedia = InputMediaUploadedPhoto | InputMediaUploadedDocument | InputMediaPhoto | InputMediaDocument


async def create_message_internal(
        user: User, peer: Peer, random_id: int | None, reply_to_message_id: int | None, clear_draft: bool, author: User,
        **message_kwargs
) -> dict[Peer, Message]:
    if random_id is not None and await Message.filter(peer=peer, random_id=str(random_id)).exists():
        raise ErrorRpc(error_code=500, error_message="RANDOM_ID_DUPLICATE")

    reply = None
    if reply_to_message_id:
        reply = await Message.get_or_none(id=reply_to_message_id, peer=peer)
        if reply is None:
            raise ErrorRpc(error_code=400, error_message="REPLY_TO_INVALID")

    peers = [peer]
    peers.extend(await peer.get_opposite())
    messages: dict[Peer, Message] = {}

    internal_id = Snowflake.make_id()
    for to_peer in peers:
        await to_peer.fetch_related("owner", "user")
        await Dialog.get_or_create(peer=to_peer)
        if to_peer == peer and random_id is not None:
            message_kwargs["random_id"] = str(random_id)
        messages[to_peer] = await Message.create(
            internal_id=internal_id,
            peer=to_peer,
            reply_to=(await Message.get_or_none(peer=to_peer, internal_id=reply.internal_id)) if reply else None,
            author=author,
            **message_kwargs
        )
        message_kwargs.pop("random_id", None)

    if clear_draft and (draft := await MessageDraft.get_or_none(dialog__peer=peer)) is not None:
        await draft.delete()
        await UpdatesManager.update_draft(user, peer, None)

    presence = await Presence.update_to_now(user)
    await UpdatesManager.update_status(user, presence, peers[1:])

    return messages


async def send_message_internal(
        user: User, peer: Peer, random_id: int | None, reply_to_message_id: int | None, clear_draft: bool, author: User,
        **message_kwargs
) -> Updates:
    messages = await create_message_internal(
        user, peer, random_id, reply_to_message_id, clear_draft, author, **message_kwargs,
    )
    if (upd := await UpdatesManager.send_message(user, messages)) is None:
        assert False, "unknown chat type ?"

    return upd


def _resolve_reply_id(request: SendMessage_148 | SendMessage | SendMedia_148 | SendMedia) -> int | None:
    if isinstance(request, (SendMessage, SendMedia)) and request.reply_to is not None:
        return request.reply_to.reply_to_msg_id
    elif isinstance(request, (SendMessage_148, SendMedia_148)) and request.reply_to_msg_id is not None:
        return request.reply_to_msg_id


@handler.on_request(SendMessage_148)
@handler.on_request(SendMessage)
async def send_message(request: SendMessage, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)

    if peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    if not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    if len(request.message) > 2000:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_TOO_LONG")

    reply_to_message_id = _resolve_reply_id(request)
    return await send_message_internal(
        user, peer, request.random_id, reply_to_message_id, request.clear_draft,
        author=user, message=request.message, entities=validate_message_entities(request.message, request.entities),
    )


@handler.on_request(UpdatePinnedMessage)
async def update_pinned_message(request: UpdatePinnedMessage, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)

    if (message := await Message.get_(request.id, peer)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    message.pinned = not request.unpin
    messages = {peer: message}

    if not request.pm_oneside and not (peer.type is PeerType.USER and (peer.blocked or not await peer.get_opposite())):
        other_messages = await Message.filter(
            peer__user=user, internal_id=message.internal_id,
        ).select_related("peer", "author")
        for other_message in other_messages:
            other_message.pinned = message.pinned
            messages[other_message.peer] = other_message

    await Message.bulk_update(messages.values(), ["pinned"])

    result = await UpdatesManager.pin_message(user, messages)

    if not request.silent and not request.pm_oneside:
        updates = await send_message_internal(
            user, peer, None, message.id, False, author=user, type=MessageType.SERVICE_PIN_MESSAGE
        )
        result.updates.extend(updates.updates)

    return result


@handler.on_request(DeleteMessages)
async def delete_messages(request: DeleteMessages, user: User):
    ids = request.id[:100]
    messages = defaultdict(list)
    for message in await Message.filter(id__in=ids, peer__owner=user).select_related("peer", "peer__user", "peer__owner"):
        messages[user].append(message.id)
        if not request.revoke:
            continue

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

    presence = await Presence.update_to_now(user)
    await UpdatesManager.update_status(user, presence, list(messages.keys()))

    return AffectedMessages(pts=pts, pts_count=len(all_ids))


@handler.on_request(EditMessage_136)
@handler.on_request(EditMessage)
async def edit_message(request: EditMessage | EditMessage_136, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)

    if peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

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
            message.message = request.message
            message.edit_date = edit_date
            message.version += 1
            messages[to_peer] = message

    await Message.bulk_update(messages.values(), ["message", "edit_date", "version"])
    presence = await Presence.update_to_now(user)
    await UpdatesManager.update_status(user, presence, peers[1:])

    return await UpdatesManager.edit_message(user, messages)


async def _process_media(user: User, media: InputMedia) -> MessageMedia:
    if not isinstance(media, (
            InputMediaUploadedDocument, InputMediaUploadedPhoto, InputMediaPhoto, InputMediaDocument
    )):
        raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

    file: File | None = None
    mime: str | None = None
    media_type: MediaType | None = None
    attributes = []

    if isinstance(media, InputMediaUploadedDocument):
        mime = media.mime_type
        media_type = MediaType.DOCUMENT
        attributes = media.attributes
    elif isinstance(media, InputMediaUploadedPhoto):
        mime = "image/jpeg"
        media_type = MediaType.PHOTO

    if isinstance(media, (InputMediaUploadedDocument, InputMediaUploadedPhoto)):
        uploaded_file = await UploadingFile.get_or_none(user=user, file_id=media.file.id)
        if uploaded_file is None:
            raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")
        file = await uploaded_file.finalize_upload(mime, attributes)
    elif isinstance(media, (InputMediaPhoto, InputMediaDocument)):
        file_access = await FileAccess.get_or_none(
            user=user, file__id=media.id.id, access_hash=media.id.access_hash, file_reference=media.id.file_reference,
            expires__gt=datetime.now(UTC)
        ).select_related("file")
        if file_access is None \
                or (not file_access.file.mime_type.startswith("image/") and isinstance(media, InputMediaPhoto)) \
                or (file_access.file.photo_sizes is None and isinstance(media, InputMediaPhoto)):
            raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

        file = file_access.file
        media_type = MediaType.PHOTO if isinstance(media, InputMediaPhoto) else MediaType.DOCUMENT

    if isinstance(media, InputMediaUploadedPhoto):
        file.photo_sizes = await resize_photo(str(file.physical_id))
        file.photo_stripped = await generate_stripped(str(file.physical_id))
        await file.save(update_fields=["photo_sizes", "photo_stripped"])

    return await MessageMedia.create(file=file, spoiler=media.spoiler, type=media_type)


@handler.on_request(SendMedia_148)
@handler.on_request(SendMedia)
async def send_media(request: SendMedia | SendMedia_148, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)

    if peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    if len(request.message) > 2000:
        raise ErrorRpc(error_code=400, error_message="MEDIA_CAPTION_TOO_LONG")

    media = await _process_media(user, request.media)
    reply_to_message_id = _resolve_reply_id(request)

    return await send_message_internal(
        user, peer, request.random_id, reply_to_message_id, request.clear_draft,
        author=user, message=request.message, media=media,
        entities=validate_message_entities(request.message, request.entities),
    )


@handler.on_request(SaveDraft)
async def save_draft(request: SaveDraft, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)

    dialog = await Dialog.get_or_create(peer=peer)
    draft, _ = await MessageDraft.get_or_create(
        dialog=dialog,
        defaults={"message": request.message, "date": datetime.now()}
    )

    await UpdatesManager.update_draft(user, peer, draft)
    return True


@handler.on_request(ForwardMessages_148)
@handler.on_request(ForwardMessages)
async def forward_messages(request: ForwardMessages | ForwardMessages_148, user: User) -> Updates:
    from_peer = None

    if isinstance(request.from_peer, InputPeerEmpty):
        first_msg = await Message.get_or_none(peer__owner=user, id=request.id[0]).select_related("peer")
        if not first_msg:
            raise ErrorRpc(error_code=400, error_message="MESSAGE_IDS_EMPTY")
        from_peer = first_msg.peer

    if (from_peer is None and (from_peer := await Peer.from_input_peer(user, request.from_peer)) is None) \
            or (to_peer := await Peer.from_input_peer(user, request.to_peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if to_peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    if not request.id:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_IDS_EMPTY")
    if len(request.id) != len(request.random_id):
        raise ErrorRpc(error_code=400, error_message="RANDOM_ID_INVALID")
    if await Message.filter(peer=to_peer, id__in=list(map(str, request.random_id[:100]))).exists():
        raise ErrorRpc(error_code=500, error_message="RANDOM_ID_DUPLICATE")

    random_ids = dict(zip(request.id[:100], request.random_id[:100]))
    messages = await Message.filter(
        peer=from_peer, id__in=request.id[:100], type=MessageType.REGULAR
    ).order_by("id").select_related("author", "media")
    reply_ids = {}

    if not messages:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_IDS_EMPTY")

    peers = [to_peer]
    peers.extend(await to_peer.get_opposite())
    result: dict[Peer, list[Message]] = {}

    for message in messages:
        internal_id = Snowflake.make_id()
        reply_ids[message.id] = internal_id

        for opp_peer in peers:
            if opp_peer not in result:
                result[opp_peer] = []

            await Dialog.get_or_create(peer=opp_peer)
            result[opp_peer].append(
                await message.clone_for_peer(
                    peer=opp_peer,
                    new_author=user,
                    internal_id=internal_id,
                    fwd=True,
                    fwd_drop_header=request.drop_author,
                    fwd_drop_captions=request.drop_media_captions,
                    random_id=random_ids.get(message.id) if opp_peer == to_peer and message.id in random_ids else None,
                    reply_to_internal_id=reply_ids.get(message.id),
                )
            )

    if to_peer.type is PeerType.SELF:
        await SavedDialog.get_or_create(peer=from_peer)

    presence = await Presence.update_to_now(user)
    await UpdatesManager.update_status(user, presence, peers[1:])

    if (upd := await UpdatesManager.send_messages(result, user)) is None:
        assert False, "unknown chat type ?"

    return upd


# TODO: DeleteHistory
# TODO: SendMultiMedia
