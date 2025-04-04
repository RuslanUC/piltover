from collections import defaultdict
from datetime import datetime, UTC, timedelta
from time import time
from typing import cast

from loguru import logger
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import resize_photo, generate_stripped, validate_message_entities
from piltover.app_config import AppConfig
from piltover.db.enums import MediaType, MessageType, PeerType, ChatBannedRights, ChatAdminRights
from piltover.db.models import User, Dialog, MessageDraft, State, Peer, MessageMedia, File, Presence, UploadingFile, \
    SavedDialog, Message, ChatParticipant, Channel, ChannelPostInfo, Poll, PollAnswer
from piltover.exceptions import ErrorRpc
from piltover.tl import Updates, InputMediaUploadedDocument, InputMediaUploadedPhoto, InputMediaPhoto, \
    InputMediaDocument, InputPeerEmpty, MessageActionPinMessage, InputMediaPoll
from piltover.tl.functions.messages import SendMessage, DeleteMessages, EditMessage, SendMedia, SaveDraft, \
    SendMessage_148, SendMedia_148, EditMessage_136, UpdatePinnedMessage, ForwardMessages, ForwardMessages_148, \
    UploadMedia, UploadMedia_136, SendMultiMedia, SendMultiMedia_148, DeleteHistory
from piltover.tl.types.messages import AffectedMessages, AffectedHistory
from piltover.utils.snowflake import Snowflake
from piltover.worker import MessageHandler

handler = MessageHandler("messages.sending")

InputMedia = InputMediaUploadedPhoto | InputMediaUploadedDocument | InputMediaPhoto | InputMediaDocument \
             | InputMediaPoll
DocOrPhotoMedia = (InputMediaUploadedDocument, InputMediaUploadedPhoto, InputMediaPhoto, InputMediaDocument)


async def send_message_internal(
        user: User, peer: Peer, random_id: int | None, reply_to_message_id: int | None, clear_draft: bool, author: User,
        opposite: bool = True, **message_kwargs
) -> Updates:
    messages = await Message.create_for_peer(
        user, peer, random_id, reply_to_message_id, author, opposite, **message_kwargs,
    )

    if clear_draft and (draft := await MessageDraft.get_or_none(dialog__peer=peer)) is not None:
        await draft.delete()
        await UpdatesManager.update_draft(user, peer, None)

    if peer.type is PeerType.CHANNEL:
        if len(messages) != 1:
            logger.warning(f"Got {len(messages)} messages after creating message with channel peer!")
            return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)
        return await UpdatesManager.send_message_channel(user, list(messages.values())[0])

    if (upd := await UpdatesManager.send_message(user, messages)) is None:
        raise NotImplementedError("unknown chat type ?")

    return cast(Updates, upd)


def _resolve_reply_id(
        request: SendMessage_148 | SendMessage | SendMedia_148 | SendMedia | SendMultiMedia_148 | SendMultiMedia,
) -> int | None:
    if isinstance(request, (SendMessage, SendMedia, SendMultiMedia)) and request.reply_to is not None:
        return request.reply_to.reply_to_msg_id
    elif isinstance(request, (SendMessage_148, SendMedia_148, SendMultiMedia_148)) and request.reply_to_msg_id is not None:
        return request.reply_to_msg_id


@handler.on_request(SendMessage_148)
@handler.on_request(SendMessage)
async def send_message(request: SendMessage, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if isinstance(chat_or_channel, Channel) \
                and not chat_or_channel.admin_has_permission(participant, ChatAdminRights.POST_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_PLAIN):
            raise ErrorRpc(error_code=403, error_message="CHAT_SEND_PLAIN_FORBIDDEN")

    if peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    if not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    if len(request.message) > AppConfig.MAX_MESSAGE_LENGTH:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_TOO_LONG")

    reply_to_message_id = _resolve_reply_id(request)

    is_channel_post = False
    post_info = None
    post_signature = None
    if peer.type is PeerType.CHANNEL and peer.channel.channel:
        is_channel_post = True
        post_info = await ChannelPostInfo.create()
        if peer.channel.signatures:
            post_signature = user.first_name

    return await send_message_internal(
        user, peer, request.random_id, reply_to_message_id, request.clear_draft,
        author=user, message=request.message, entities=validate_message_entities(request.message, request.entities),
        channel_post=is_channel_post, post_info=post_info, post_author=post_signature,
    )


@handler.on_request(UpdatePinnedMessage)
async def update_pinned_message(request: UpdatePinnedMessage, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.PIN_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")

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
            user, peer, None, message.id, False, author=user, type=MessageType.SERVICE_PIN_MESSAGE,
            extra_info=MessageActionPinMessage().write(),
        )
        result.updates.extend(updates.updates)

    return result


@handler.on_request(DeleteMessages)
async def delete_messages(request: DeleteMessages, user: User):
    # TODO: check if message peer is chat and user has permission to revoke messages (if request.revoke is True)

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
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")

    if peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    if peer.type is PeerType.CHANNEL:
        message = await Message.get_or_none(
            id=request.id, peer__owner=None, peer__channel=peer.channel, type=MessageType.REGULAR
        ).select_related("peer", "author", "media")
    else:
        message = await Message.get_(request.id, peer)
    if message is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if message.media_id is None and not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    elif message.media_id is None and request.media:
        raise ErrorRpc(error_code=400, error_message="MEDIA_PREV_INVALID")
    elif message.media_id is not None and request.media and not isinstance(request.media, DocOrPhotoMedia):
        raise ErrorRpc(error_code=400, error_message="MEDIA_NEW_INVALID")
    elif message.media_id is not None and request.media \
            and message.media.type not in (MediaType.DOCUMENT, MediaType.PHOTO):
        raise ErrorRpc(error_code=400, error_message="MEDIA_NEW_INVALID")

    media = None
    if request.media is not None:
        media = await _process_media(user, request.media)
        if media.id == message.media_id or media.file_id == message.media.file_id:
            raise ErrorRpc(error_code=400, error_message="MEDIA_NEW_INVALID")

    # For some reason PyCharm keeps complaining about request.message "Expected type 'Sized', got 'Message' instead"
    message_text = cast(str | None, request.message)

    if request.message is not None and len(message_text) > AppConfig.MAX_MESSAGE_LENGTH and not message.media_id:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_TOO_LONG")
    elif request.message is not None and len(message_text) > AppConfig.MAX_CAPTION_LENGTH and message.media_id:
        raise ErrorRpc(error_code=400, error_message="MEDIA_CAPTION_TOO_LONG")
    if message.author != user:
        raise ErrorRpc(error_code=403, error_message="MESSAGE_AUTHOR_REQUIRED")
    if message.message == request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_NOT_MODIFIED")

    if peer.type is PeerType.CHANNEL:
        if message_text is not None:
            message.message = message_text
        if media is not None:
            message.media = media
        message.edit_date = datetime.now(UTC)
        message.version += 1
        await message.save(update_fields=["message", "edit_date", "version", "media_id"])
        message.peer.channel = peer.channel
        return await UpdatesManager.edit_message_channel(user, message)

    peers = [peer]
    peers.extend(await peer.get_opposite())
    messages: dict[Peer, Message] = {}

    edit_date = datetime.now(UTC)
    for to_peer in peers:
        message = await Message.get_or_none(
            internal_id=message.internal_id, peer=to_peer,
        ).select_related("author", "peer")
        if message is not None:
            if message_text is not None:
                message.message = message_text
            if media is not None:
                message.media = media
            message.edit_date = edit_date
            message.version += 1
            messages[to_peer] = message

    await Message.bulk_update(messages.values(), ["message", "edit_date", "version", "media_id"])
    presence = await Presence.update_to_now(user)
    await UpdatesManager.update_status(user, presence, peers[1:])

    return await UpdatesManager.edit_message(user, messages)


async def _process_media(user: User, media: InputMedia) -> MessageMedia:
    if not isinstance(media, (*DocOrPhotoMedia, InputMediaPoll,)):
        raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

    file: File | None = None
    poll: Poll | None = None
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
    elif isinstance(media, InputMediaPoll):
        media_type = MediaType.POLL

    if isinstance(media, (InputMediaUploadedDocument, InputMediaUploadedPhoto)):
        uploaded_file = await UploadingFile.get_or_none(user=user, file_id=media.file.id)
        if uploaded_file is None:
            raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")
        file = await uploaded_file.finalize_upload(mime, attributes)
    elif isinstance(media, (InputMediaPhoto, InputMediaDocument)):
        file = await File.get_or_none(
            id=media.id.id, fileaccesss__user=user, fileaccesss__access_hash=media.id.access_hash,
            fileaccesss__file_reference=media.id.file_reference, fileaccesss__expires__gt=datetime.now(UTC),
        )
        if file is None \
                or (not file.mime_type.startswith("image/") and isinstance(media, InputMediaPhoto)) \
                or (file.photo_sizes is None and isinstance(media, InputMediaPhoto)):
            raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

        media_type = MediaType.PHOTO if isinstance(media, InputMediaPhoto) else MediaType.DOCUMENT
    elif isinstance(media, InputMediaPoll):
        if media.poll.quiz and media.poll.multiple_choice:
            raise ErrorRpc(error_code=400, error_message="QUIZ_MULTIPLE_INVALID")
        if media.poll.quiz and not media.correct_answers:
            raise ErrorRpc(error_code=400, error_message="QUIZ_CORRECT_ANSWERS_EMPTY")
        if media.poll.quiz and len(media.correct_answers) > 1:
            raise ErrorRpc(error_code=400, error_message="QUIZ_CORRECT_ANSWERS_TOO_MUCH")
        if not media.poll.question or len(media.poll.question) > 255:
            raise ErrorRpc(error_code=400, error_message="POLL_QUESTION_INVALID")
        if len(media.poll.answers) < 2 or len(media.poll.answers) > 10:
            raise ErrorRpc(error_code=400, error_message="POLL_ANSWERS_INVALID")
        if media.poll.quiz and media.solution is not None \
                and (len(media.solution) > 200 or media.solution.count("\n") > 2):
            raise ErrorRpc(error_code=400, error_message="POLL_ANSWERS_INVALID")
        answers = set()
        for answer in media.poll.answers:
            if answer.option in answers:
                raise ErrorRpc(error_code=400, error_message="POLL_OPTION_DUPLICATE")
            if not answer.option or len(answer.option) > 100 or not answer.text or len(answer.text) > 100:
                raise ErrorRpc(error_code=400, error_message="POLL_ANSWER_INVALID")
        if media.poll.quiz and media.correct_answers[0] not in answers:
            raise ErrorRpc(error_code=400, error_message="QUIZ_CORRECT_ANSWER_INVALID")

        correct_option = media.correct_answers[0] if media.poll.quiz else None

        ends_at = None
        if media.poll.close_period and 5 < media.poll.close_period <= 600:
            ends_at = datetime.now(UTC) + timedelta(seconds=media.poll.close_period)
        elif media.poll.close_date:
            close_datetime = datetime.fromtimestamp(media.poll.close_date, UTC)
            if 5 < (close_datetime - datetime.now(UTC)).seconds <= 600:
                ends_at = datetime.fromtimestamp(media.poll.close_date, UTC)

        async with in_transaction():
            poll = await Poll.create(
                quiz=media.poll.quiz,
                public_voters=media.poll.public_voters,
                multiple_choices=media.poll.multiple_choice,
                question=media.poll.question,
                solution=media.solution if media.poll.quiz else None,
                ends_at=ends_at,
            )
            await PollAnswer.bulk_create([
                PollAnswer(poll=poll, text=answer.text, option=answer.option, correct=answer.option == correct_option)
                for answer in media.poll.answers
            ])

    if isinstance(media, InputMediaUploadedPhoto):
        file.photo_sizes = await resize_photo(str(file.physical_id))
        file.photo_stripped = await generate_stripped(str(file.physical_id))
        await file.save(update_fields=["photo_sizes", "photo_stripped"])

    return await MessageMedia.create(file=file, spoiler=getattr(media, "spoiler", False), type=media_type, poll=poll)


@handler.on_request(SendMedia_148)
@handler.on_request(SendMedia)
async def send_media(request: SendMedia | SendMedia_148, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MEDIA):
            raise ErrorRpc(error_code=403, error_message="CHAT_SEND_GIFS_FORBIDDEN")

    if peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    if len(request.message) > AppConfig.MAX_CAPTION_LENGTH:
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
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        await peer.chat_or_channel.get_participant_raise(user)

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

    if from_peer is None and (from_peer := await Peer.from_input_peer(user, request.from_peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    if from_peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        await from_peer.chat_or_channel.get_participant_raise(user)
    if from_peer.type in (PeerType.CHAT, PeerType.CHANNEL) and from_peer.chat_or_channel.no_forwards:
        raise ErrorRpc(error_code=406, error_message="CHAT_FORWARDS_RESTRICTED")

    # TODO: check if from_peer is channel and user has access to messages

    if (to_peer := await Peer.from_input_peer(user, request.to_peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    if to_peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")
    if to_peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = to_peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")

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
    media_group_ids: defaultdict[int | None, int | None] = defaultdict(Snowflake.make_id)
    media_group_ids[None] = None

    if not messages:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_IDS_EMPTY")

    if to_peer.type is PeerType.CHANNEL:
        peers = [await Peer.get_or_none(owner=None, channel=to_peer.channel)]
    else:
        peers = [to_peer, *(await to_peer.get_opposite())]
    result: defaultdict[Peer, list[Message]] = defaultdict(list)

    for message in messages:
        internal_id = Snowflake.make_id()
        reply_ids[message.id] = internal_id

        for opp_peer in peers:
            if opp_peer.owner_id is not None:
                await Dialog.get_or_create(peer=opp_peer)
            result[opp_peer].append(
                await message.clone_for_peer(
                    peer=opp_peer,
                    new_author=user,
                    internal_id=internal_id,
                    drop_captions=request.drop_media_captions,
                    random_id=random_ids.get(message.id) if opp_peer == to_peer else None,
                    reply_to_internal_id=reply_ids.get(message.reply_to_id),
                    media_group_id=media_group_ids[message.media_group_id],
                    drop_author=request.drop_author,

                    fwd_header=await message.create_fwd_header(opp_peer) if not request.drop_author else None,
                )
            )

    if to_peer.type is PeerType.SELF:
        await SavedDialog.get_or_create(peer=from_peer)

    if to_peer.type is PeerType.CHANNEL:
        if len(result) != 1:
            raise RuntimeError("`result` contains multiple peers, but should contain only one - channel peer")
        return await UpdatesManager.send_messages_channel(next(iter(result.values())), to_peer.channel, user)

    presence = await Presence.update_to_now(user)
    await UpdatesManager.update_status(user, presence, peers[1:])

    if (upd := await UpdatesManager.send_messages(result, user)) is None:
        raise NotImplementedError("unknown chat type ?")

    return upd


@handler.on_request(UploadMedia_136)
@handler.on_request(UploadMedia)
async def upload_media(request: UploadMedia | UploadMedia_136, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MEDIA):
            raise ErrorRpc(error_code=403, error_message="CHAT_SEND_GIFS_FORBIDDEN")

    if peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    media = await _process_media(user, request.media)
    return await media.to_tl(user)


@handler.on_request(SendMultiMedia_148)
@handler.on_request(SendMultiMedia)
async def send_multi_media(request: SendMultiMedia | SendMultiMedia_148, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MEDIA):
            raise ErrorRpc(error_code=403, error_message="CHAT_SEND_GIFS_FORBIDDEN")

    if peer.blocked:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")
    if not request.multi_media:
        raise ErrorRpc(error_code=400, error_message="MEDIA_EMPTY")
    if len(request.multi_media) > 10:
        raise ErrorRpc(error_code=400, error_message="MULTI_MEDIA_TOO_LONG")

    reply_to_message_id = _resolve_reply_id(request)
    if reply_to_message_id and not await Message.filter(id=reply_to_message_id, peer=peer).exists():
        raise ErrorRpc(error_code=400, error_message="REPLY_TO_INVALID")

    messages: list[tuple[str, int, MessageMedia, list[dict] | None]] = []
    for single_media in request.multi_media:
        if len(single_media.message) > AppConfig.MAX_CAPTION_LENGTH:
            raise ErrorRpc(error_code=400, error_message="MEDIA_CAPTION_TOO_LONG")
        if not single_media.random_id:
            raise ErrorRpc(error_code=400, error_message="RANDOM_ID_EMPTY")

        if not isinstance(single_media.media, (InputMediaPhoto, InputMediaDocument)):
            raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

        media_id = single_media.media.id
        media = await MessageMedia.get_or_none(
            file__id=media_id.id, file__fileaccesss__user=user, file__fileaccesss__access_hash=media_id.access_hash,
            file__fileaccesss__file_reference=media_id.file_reference, file__fileaccesss__expires__gt=datetime.now(UTC),
        )

        messages.append((
            single_media.message,
            single_media.random_id,
            media,
            validate_message_entities(single_media.message, single_media.entities),
        ))

    if await Message.filter(peer=peer, random_id__in=[str(random_id) for _, random_id, _, _ in messages]).exists():
        raise ErrorRpc(error_code=500, error_message="RANDOM_ID_DUPLICATE")

    group_id = Snowflake.make_id()

    updates = None
    for message, random_id, media, entities in messages:
        new_updates = await send_message_internal(
            user, peer, random_id, reply_to_message_id, request.clear_draft,
            author=user, message=message, media=media, entities=entities, media_group_id=group_id,
        )
        if updates is None:
            updates = new_updates
            continue

        updates.updates.extend(new_updates.updates)

    return updates


@handler.on_request(DeleteHistory)
async def delete_history(request: DeleteHistory, user: User) -> AffectedHistory:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    query = Q(peer=peer)
    if request.max_id:
        query &= Q(id__lte=request.max_id)
    if request.min_date:
        query &= Q(date__gte=datetime.fromtimestamp(request.min_date, UTC))
    if request.max_date:
        query &= Q(date__lte=datetime.fromtimestamp(request.max_date, UTC))

    messages: defaultdict[User, list[int]] = defaultdict(list)
    offset_id = 0

    message: Message
    async for message in Message.filter(query).order_by("-id").limit(1001):
        if len(messages[user]) == 1000:
            offset_id = message.id
            break

        messages[user].append(message.id)

        if not request.revoke:
            continue

        # TODO: delete history for each user separately if request.revoke
        #  (so messages that current user already deleted without revoke will be deleted too)
        #  (maybe just call delete_history for each user (opposite_peer)?)

        for opposite_peer in await message.peer.get_opposite():
            opp_message = await Message.get_or_none(internal_id=message.internal_id, peer=opposite_peer)
            if opp_message is not None:
                messages[message.peer.user].append(opp_message.id)

    all_ids = [i for ids in messages.values() for i in ids]
    if not all_ids:
        updates_state, _ = await State.get_or_create(user=user)
        return AffectedHistory(pts=updates_state.pts, pts_count=0, offset=0)

    await Message.filter(id__in=all_ids).delete()
    pts = await UpdatesManager.delete_messages(user, messages)

    if not offset_id:
        # TODO: delete for other users if request.revoke
        await Dialog.filter(peer=peer).delete()
        if peer.type == PeerType.CHAT:
            await ChatParticipant.filter(char=peer.chat, user=user).delete()
            await peer.delete()
            await UpdatesManager.update_chat(peer.chat, user)

    return AffectedHistory(pts=pts, pts_count=len(messages[user]), offset=offset_id)
