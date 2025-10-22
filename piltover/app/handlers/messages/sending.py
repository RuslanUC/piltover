from array import array
from collections import defaultdict
from datetime import datetime, UTC, timedelta
from time import time
from typing import cast

from loguru import logger
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers import bots
from piltover.app.utils.utils import process_message_entities
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import MediaType, MessageType, PeerType, ChatBannedRights, ChatAdminRights, FileType
from piltover.db.models import User, Dialog, MessageDraft, State, Peer, MessageMedia, File, Presence, UploadingFile, \
    SavedDialog, Message, ChatParticipant, Channel, ChannelPostInfo, Poll, PollAnswer, FileAccess, MessageMention, \
    TaskIqScheduledMessage
from piltover.exceptions import ErrorRpc
from piltover.tl import Updates, InputMediaUploadedDocument, InputMediaUploadedPhoto, InputMediaPhoto, \
    InputMediaDocument, InputPeerEmpty, MessageActionPinMessage, InputMediaPoll, InputMediaUploadedDocument_133, \
    InputMediaDocument_133, TextWithEntities, InputMediaEmpty, MessageEntityMention, MessageEntityMentionName, \
    LongVector, DocumentAttributeFilename
from piltover.tl.functions.messages import SendMessage, DeleteMessages, EditMessage, SendMedia, SaveDraft, \
    SendMessage_148, SendMedia_148, EditMessage_133, UpdatePinnedMessage, ForwardMessages, ForwardMessages_148, \
    UploadMedia, UploadMedia_133, SendMultiMedia, SendMultiMedia_148, DeleteHistory, SendMessage_176, SendMedia_176, \
    ForwardMessages_176
from piltover.tl.types.messages import AffectedMessages, AffectedHistory
from piltover.utils.snowflake import Snowflake
from piltover.worker import MessageHandler

handler = MessageHandler("messages.sending")

InputMedia = InputMediaUploadedPhoto | InputMediaUploadedDocument | InputMediaPhoto | InputMediaDocument \
             | InputMediaPoll
DocOrPhotoMedia = (
    InputMediaUploadedDocument, InputMediaUploadedDocument_133, InputMediaUploadedPhoto, InputMediaPhoto,
    InputMediaDocument, InputMediaDocument_133,
)


async def _extract_mentions_from_message(entities: list[dict], text: str, author: User) -> set[int]:
    mentioned_user_ids = set()
    mentioned_usernames = set()

    for entity in entities:
        tl_id = entity["_"]
        if tl_id == MessageEntityMention.tlid():
            offset = entity["offset"]
            length = entity["length"]
            mentioned_usernames.add(text[offset + 1:offset + length])
        elif tl_id == MessageEntityMentionName.tlid():
            mentioned_user_ids.add(entity["user_id"])

    if not mentioned_usernames and not mentioned_user_ids:
        return set()

    query = Q()
    if mentioned_usernames:
        query |= Q(usernames__username__in=list(mentioned_usernames))
    if mentioned_user_ids:
        query |= Q(id__in=list(mentioned_user_ids))

    return set(
        await User.filter(id__not=author.id).filter(query).values_list("id", flat=True)
    )


async def send_created_messages_internal(
        messages: dict[Peer, Message], opposite: bool, peer: Peer, user: User, clear_draft: bool,
        mentioned_user_ids: set[int],
) -> Updates:
    if opposite and peer.type is not PeerType.CHANNEL:
        presence = await Presence.update_to_now(user)
        await upd.update_status(user, presence, await peer.get_opposite())

    if opposite and peer.type is PeerType.CHAT and mentioned_user_ids:
        mentioned_peers = [
            message_peer
            for message_peer in messages
            if message_peer.owner_id in mentioned_user_ids
        ]

        unread_mentions_to_create = []
        for mentioned_peer in mentioned_peers:
            unread_mentions_to_create.append(MessageMention(peer=mentioned_peer, message=messages[mentioned_peer]))

        if unread_mentions_to_create:
            await MessageMention.bulk_create(unread_mentions_to_create)

    if clear_draft and (draft := await MessageDraft.get_or_none(dialog__peer=peer)) is not None:
        await draft.delete()
        await upd.update_draft(user, peer, None)

    if peer.type is PeerType.CHANNEL:
        if len(messages) != 1:
            logger.warning(f"Got {len(messages)} messages after creating message with channel peer!")
            return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

        message = list(messages.values())[0]

        if mentioned_user_ids:
            mentioned_peers = await Peer.filter(owner__id__in=list(mentioned_user_ids), channel__id=peer.channel_id)
            unread_mentions_to_create = []
            for mentioned_peer in mentioned_peers:
                unread_mentions_to_create.append(MessageMention(peer=mentioned_peer, message=message))

            if unread_mentions_to_create:
                await MessageMention.bulk_create(unread_mentions_to_create)

        return await upd.send_message_channel(user, message)

    if (update := await upd.send_message(user, messages)) is None:
        raise RuntimeError("unreachable ?")

    if peer.user and peer.user.bot and await peer.user.get_raw_username() in bots.HANDLERS:
        bot_message = await bots.process_message_to_bot(peer, messages[peer])
        if bot_message is not None:
            if (bot_upd := await upd.send_message(user, {peer: bot_message})) is None:
                raise RuntimeError("unreachable ?")
            update.users.extend(bot_upd.users)
            update.chats.extend(bot_upd.chats)
            update.updates.extend(bot_upd.updates)

    return cast(Updates, update)


async def send_message_internal(
        user: User, peer: Peer, random_id: int | None, reply_to_message_id: int | None, clear_draft: bool, author: User,
        opposite: bool = True, scheduled_date: int | None = None, **message_kwargs
) -> Updates:
    if opposite and peer.user and peer.user.bot and await peer.user.get_raw_username() in bots.HANDLERS:
        opposite = False

    mentioned_user_ids = set()
    entities: list[dict[str, int | str]]

    message_text = message_kwargs.get("message")
    if opposite and peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        if (entities := message_kwargs.get("entities")) and message_text:
            mentioned_user_ids = await _extract_mentions_from_message(entities, message_text, author)

        if reply_to_message_id:
            peer_filter = {"peer__channel": peer.channel} if peer.type is PeerType.CHANNEL else {"peer": peer}
            reply_author_id = cast(int, await Message.get_or_none(
                id=reply_to_message_id, **peer_filter,
            ).values_list("author__id", flat=True))
            if reply_author_id is not None and reply_author_id != author.id:
                mentioned_user_ids.add(reply_author_id)

    schedule = False
    real_opposite = opposite
    if scheduled_date is not None and (scheduled_date - AppConfig.SCHEDULED_INSTANT_SEND_THRESHOLD) > time():
        schedule = True
        opposite = False
        message_kwargs["scheduled_date"] = datetime.fromtimestamp(scheduled_date, UTC)
        message_kwargs["type"] = MessageType.SCHEDULED

    messages = await Message.create_for_peer(
        peer, random_id, reply_to_message_id, author, opposite, **message_kwargs,
    )

    if schedule:
        message = messages[peer]

        mentioned_users = None
        if mentioned_user_ids:
            ids = array("q", mentioned_user_ids)
            mentioned_users = LongVector.write(ids)[8:]

        await TaskIqScheduledMessage.create(
            scheduled_time=scheduled_date,
            message=message,
            mentioned_users=mentioned_users,
            opposite=real_opposite,
        )

        return await upd.new_scheduled_message(user, message)

    return await send_created_messages_internal(messages, opposite, peer, user, clear_draft, mentioned_user_ids)


SendMessageTypes = SendMessage_148 | SendMessage_176 | SendMessage | SendMedia_148 | SendMedia_176 | SendMedia \
                   | SendMultiMedia_148 | SendMultiMedia


def _resolve_reply_id(
        request: SendMessageTypes,
) -> int | None:
    if isinstance(request, (SendMessage, SendMedia, SendMultiMedia, SendMessage_176, SendMedia_176)) \
            and request.reply_to is not None:
        return request.reply_to.reply_to_msg_id
    elif isinstance(request, (SendMessage_148, SendMedia_148, SendMultiMedia_148)) \
            and request.reply_to_msg_id is not None:
        return request.reply_to_msg_id


@handler.on_request(SendMessage_148)
@handler.on_request(SendMessage_176)
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

    if peer.blocked_at is not None:
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
        author=user, message=request.message, scheduled_date=request.schedule_date,
        entities=await process_message_entities(request.message, request.entities, user),
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

    if not request.pm_oneside \
            and not (peer.type is PeerType.USER and (peer.blocked_at is not None or not await peer.get_opposite())):
        other_messages = await Message.filter(
            peer__user=user, internal_id=message.internal_id,
        ).select_related("peer", "author")
        for other_message in other_messages:
            other_message.pinned = message.pinned
            messages[other_message.peer] = other_message

    await Message.bulk_update(messages.values(), ["pinned"])

    result = await upd.pin_message(user, messages)

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
    for message in await Message.filter(id__in=ids, peer__owner=user).select_related(
            "peer", "peer__user", "peer__owner",
    ):
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
    pts = await upd.delete_messages(user, messages)

    presence = await Presence.update_to_now(user)
    await upd.update_status(user, presence, list(messages.keys()))

    return AffectedMessages(pts=pts, pts_count=len(all_ids))


@handler.on_request(EditMessage_133)
@handler.on_request(EditMessage)
async def edit_message(request: EditMessage | EditMessage_133, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")

    if peer.blocked_at is not None:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    if peer.type is PeerType.CHANNEL:
        message = await Message.get_or_none(
            Q(type=MessageType.REGULAR) | Q(type=MessageType.SCHEDULED),
            id=request.id, peer__owner=None, peer__channel=peer.channel,
        ).select_related("peer", "author", "media")
    else:
        message = await Message.get_(request.id, peer, (MessageType.REGULAR, MessageType.SCHEDULED))
    if message is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    new_has_media = request.media is not None and not isinstance(request.media, InputMediaEmpty)
    if message.media_id is None and not request.message and not request.schedule_date:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    elif message.media_id is None and new_has_media:
        raise ErrorRpc(error_code=400, error_message="MEDIA_PREV_INVALID")
    elif message.media_id is not None and new_has_media and not isinstance(request.media, DocOrPhotoMedia):
        raise ErrorRpc(error_code=400, error_message="MEDIA_NEW_INVALID")
    elif message.media_id is not None and request.media \
            and message.media.type not in (MediaType.DOCUMENT, MediaType.PHOTO):
        raise ErrorRpc(error_code=400, error_message="MEDIA_NEW_INVALID")

    media = None
    if new_has_media:
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

    entities = None
    if message_text is not None:
        entities = await process_message_entities(message_text, request.entities, user)

    def _edit_message(m: Message, new_edit_date: datetime | None) -> None:
        if message_text is not None:
            m.message = message_text
            if entities is not None:
                m.entities = entities
        if media is not None:
            m.media = media
        m.edit_date = new_edit_date
        m.version += 1

    # TODO: process mentioned users

    if message.scheduled_date is not None:
        _edit_message(message, None)
        if request.schedule_date is not None:
            if request.schedule_date < time() - 30:
                raise ErrorRpc(error_code=400, error_message="SCHEDULE_DATE_INVALID")
            message.scheduled_date = datetime.fromtimestamp(request.schedule_date, UTC)
            await TaskIqScheduledMessage.filter(message=message).update(scheduled_time=request.schedule_date)

        await message.save(update_fields=["message", "version", "media_id", "entities", "scheduled_date"])
        return await upd.edit_message(user, {peer: message})

    if peer.type is PeerType.CHANNEL:
        _edit_message(message, datetime.now(UTC))
        await message.save(update_fields=["message", "edit_date", "version", "media_id", "entities"])
        message.peer.channel = peer.channel
        return await upd.edit_message_channel(user, message)

    peers = [peer]
    peers.extend(await peer.get_opposite())
    messages: dict[Peer, Message] = {}

    edit_date = datetime.now(UTC)
    for message in await Message.filter(
            internal_id=message.internal_id, peer__id__in=[p.id for p in peers],
    ).select_related("author", "peer", "peer__owner", "peer__user"):
        _edit_message(message, edit_date)
        messages[message.peer] = message

    await Message.bulk_update(messages.values(), ["message", "edit_date", "version", "media_id", "entities"])
    presence = await Presence.update_to_now(user)
    await upd.update_status(user, presence, peers[1:])

    return await upd.edit_message(user, messages)


async def _get_media_thumb(
        user: User, media: InputMediaUploadedDocument | InputMediaUploadedDocument_133,
) -> bytes | None:
    if media.thumb is None:
        return None

    uploaded_thumb = await UploadingFile.get_or_none(user=user, file_id=media.thumb.id)
    if uploaded_thumb is None \
            or uploaded_thumb.mime is None \
            or not uploaded_thumb.mime.startswith("image/"):
        return None

    storage = request_ctx.get().storage
    try:
        thumb_file = await uploaded_thumb.finalize_upload(
            storage, "application/vnd.thumbnail", [], FileType.DOCUMENT, force_fallback_mime=True,
        )
    except ErrorRpc as e:
        logger.opt(exception=e).warning("Failed to process thumbnail!")
        return None

    if thumb_file.size > 1024 * 1024 * 2:
        return None

    return await storage.documents.get_part(thumb_file.physical_id, 0, 1024 * 1024 * 2)


async def _process_media(user: User, media: InputMedia) -> MessageMedia:
    if not isinstance(media, (*DocOrPhotoMedia, InputMediaPoll,)):
        raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

    file: File | None = None
    poll: Poll | None = None
    mime: str | None = None
    media_type: MediaType | None = None
    attributes = []

    if isinstance(media, (InputMediaUploadedDocument, InputMediaUploadedDocument_133)):
        mime = media.mime_type
        media_type = MediaType.DOCUMENT
        attributes = media.attributes
    elif isinstance(media, InputMediaUploadedPhoto):
        mime = "image/jpeg"
        media_type = MediaType.PHOTO
    elif isinstance(media, InputMediaPoll):
        media_type = MediaType.POLL

    if isinstance(media, (InputMediaUploadedDocument, InputMediaUploadedDocument_133, InputMediaUploadedPhoto)):
        uploaded_file = await UploadingFile.get_or_none(user=user, file_id=media.file.id)
        if uploaded_file is None:
            raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")

        storage = request_ctx.get().storage
        thumb_bytes = None

        if isinstance(media, InputMediaUploadedPhoto):
            file_type = FileType.PHOTO
        else:
            file_type = FileType.DOCUMENT
            thumb_bytes = await _get_media_thumb(user, media)

        if media.file.name:
            attributes.insert(0, DocumentAttributeFilename(file_name=media.file.name))
        file = await uploaded_file.finalize_upload(storage, mime, attributes, file_type, thumb_bytes=thumb_bytes)
    elif isinstance(media, (InputMediaPhoto, InputMediaDocument, InputMediaDocument_133)):
        valid, const = FileAccess.is_file_ref_valid(media.id.file_reference, user.id, media.id.id)
        if not valid:
            raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")
        file_q = Q(id=media.id.id)
        if const:
            file_q &= Q(constant_access_hash=media.id.access_hash, constant_file_ref=media.id.file_reference[12:])
        else:
            file_q &= Q(fileaccesss__user=user, fileaccesss__access_hash=media.id.access_hash)
        file = await File.get_or_none(file_q)
        if file is None \
                or (not file.mime_type.startswith("image/") and isinstance(media, InputMediaPhoto)) \
                or (file.photo_sizes is None and isinstance(media, InputMediaPhoto)):
            raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

        media_type = MediaType.PHOTO if isinstance(media, InputMediaPhoto) else MediaType.DOCUMENT
    elif isinstance(media, InputMediaPoll):
        # TODO: support poll question entities
        if isinstance(media.poll.question, TextWithEntities):
            poll_question_text = media.poll.question.text
        else:
            poll_question_text = media.poll.question

        if media.poll.quiz and media.poll.multiple_choice:
            raise ErrorRpc(error_code=400, error_message="QUIZ_MULTIPLE_INVALID")
        if media.poll.quiz and not media.correct_answers:
            raise ErrorRpc(error_code=400, error_message="QUIZ_CORRECT_ANSWERS_EMPTY")
        if media.poll.quiz and len(media.correct_answers) > 1:
            raise ErrorRpc(error_code=400, error_message="QUIZ_CORRECT_ANSWERS_TOO_MUCH")
        if not poll_question_text or len(poll_question_text) > 255:
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
            # TODO: support poll answers entities
            if isinstance(answer.text, TextWithEntities):
                answer_text = answer.text.text
            else:
                answer_text = answer.text
            if not answer.option or len(answer.option) > 100 or not answer_text or len(answer_text) > 100:
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

    return await MessageMedia.create(file=file, spoiler=getattr(media, "spoiler", False), type=media_type, poll=poll)


@handler.on_request(SendMedia_148)
@handler.on_request(SendMedia_176)
@handler.on_request(SendMedia)
async def send_media(request: SendMedia | SendMedia_148 | SendMedia_176, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MEDIA):
            raise ErrorRpc(error_code=403, error_message="CHAT_SEND_GIFS_FORBIDDEN")

    if peer.blocked_at is not None:
        raise ErrorRpc(error_code=400, error_message="YOU_BLOCKED_USER")

    if len(request.message) > AppConfig.MAX_CAPTION_LENGTH:
        raise ErrorRpc(error_code=400, error_message="MEDIA_CAPTION_TOO_LONG")

    media = await _process_media(user, request.media)
    reply_to_message_id = _resolve_reply_id(request)

    return await send_message_internal(
        user, peer, request.random_id, reply_to_message_id, request.clear_draft, scheduled_date=request.schedule_date,
        author=user, message=request.message, media=media,
        entities=await process_message_entities(request.message, request.entities, user),
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

    await upd.update_draft(user, peer, draft)
    return True


@handler.on_request(ForwardMessages_148)
@handler.on_request(ForwardMessages_176)
@handler.on_request(ForwardMessages)
async def forward_messages(
        request: ForwardMessages | ForwardMessages_148 | ForwardMessages_176, user: User,
) -> Updates:
    from_peer = None

    if isinstance(request.from_peer, InputPeerEmpty):
        first_msg = await Message.get_or_none(peer__owner=user, id=request.id[0]).select_related(
            "peer", "peer__chat", "peer__channel",
        )
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
    if to_peer.blocked_at is not None:
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

    # TODO: schedule_date

    for message in messages:
        internal_id = Snowflake.make_id()
        reply_ids[message.id] = internal_id

        for opp_peer in peers:
            logger.trace(
                f"Creating forwarded message for peer {opp_peer.id}({opp_peer.owner_id}) -> {opp_peer.user_id}"
            )
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
                    is_forward=True,
                )
            )

    if to_peer.type is PeerType.SELF:
        await SavedDialog.get_or_create(peer=from_peer)

    if to_peer.type is PeerType.CHANNEL:
        if len(result) != 1:
            raise RuntimeError("`result` contains multiple peers, but should contain only one - channel peer")
        return await upd.send_messages_channel(next(iter(result.values())), to_peer.channel, user)

    presence = await Presence.update_to_now(user)
    await upd.update_status(user, presence, peers[1:])

    if (update := await upd.send_messages(result, user)) is None:
        raise NotImplementedError("unknown chat type ?")

    return update


@handler.on_request(UploadMedia_133)
@handler.on_request(UploadMedia)
async def upload_media(request: UploadMedia | UploadMedia_133, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.SEND_MEDIA):
            raise ErrorRpc(error_code=403, error_message="CHAT_SEND_GIFS_FORBIDDEN")

    if peer.blocked_at is not None:
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

    if peer.blocked_at is not None:
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

        if not isinstance(single_media.media, (InputMediaPhoto, InputMediaDocument, InputMediaDocument_133)):
            raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")

        media_id = single_media.media.id

        valid, const = FileAccess.is_file_ref_valid(media_id.file_reference, user.id, media_id.id)
        if not valid:
            raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")  # TODO: FILE_REFERENCE_%d_EXPIRED ?
        media_q = Q(file__id=media_id.id)
        if const:
            file_ref = media_id.file_reference[12:]
            media_q &= Q(file__constant_access_hash=media_id.access_hash, file__constant_file_ref=file_ref)
        else:
            media_q &= Q(file__fileaccesss__user=user, file__fileaccesss__access_hash=media_id.access_hash)

        media = await MessageMedia.get_or_none(media_q)

        messages.append((
            single_media.message,
            single_media.random_id,
            media,
            await process_message_entities(single_media.message, single_media.entities, user),
        ))

    if await Message.filter(peer=peer, random_id__in=[str(random_id) for _, random_id, _, _ in messages]).exists():
        raise ErrorRpc(error_code=500, error_message="RANDOM_ID_DUPLICATE")

    group_id = Snowflake.make_id()

    updates = None
    for message, random_id, media, entities in messages:
        new_updates = await send_message_internal(
            user, peer, random_id, reply_to_message_id, request.clear_draft, scheduled_date=request.schedule_date,
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

    internal_ids: list[int] = []
    messages: defaultdict[User, list[int]] = defaultdict(list)
    offset_id = 0

    message: Message
    for message in await Message.filter(query).order_by("-id").limit(1001):
        if len(messages[user]) == 1000:
            offset_id = message.id
            break

        messages[user].append(message.id)
        internal_ids.append(message.internal_id)

    if request.revoke:
        for opposite_peer in await peer.get_opposite():
            # TODO: delete history for each user separately if request.revoke
            #  (so messages that current user already deleted without revoke will be deleted too)
            #  (maybe just call delete_history for each user (opposite_peer)?)

            ids = await Message.filter(internal__id__in=internal_ids, peer=opposite_peer).values_list("id", flat=True)
            messages[opposite_peer.owner] = ids

    all_ids = [i for ids in messages.values() for i in ids]
    if not all_ids:
        updates_state, _ = await State.get_or_create(user=user)
        return AffectedHistory(pts=updates_state.pts, pts_count=0, offset=0)

    await Message.filter(id__in=all_ids).delete()
    pts = await upd.delete_messages(user, messages)

    if not offset_id:
        # TODO: delete for other users if request.revoke
        await Dialog.filter(peer=peer).delete()
        if peer.type == PeerType.CHAT:
            await ChatParticipant.filter(char=peer.chat, user=user).delete()
            await peer.delete()
            await upd.update_chat(peer.chat, user)

    return AffectedHistory(pts=pts, pts_count=len(messages[user]), offset=offset_id)
