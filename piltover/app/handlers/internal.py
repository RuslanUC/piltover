from datetime import datetime, UTC, timedelta
from typing import cast

from loguru import logger
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers import bots
from piltover.app.handlers.messages.sending import send_created_messages_internal, _resolve_noforwards, \
    _extract_mentions_from_message
from piltover.config import SYSTEM_CONFIG
from piltover.db.enums import PeerType, ScheduledTaskType, ScheduledTaskState
from piltover.db.models import Peer, MessageRef, User, Presence, MessageDraft, TelegramUser
from piltover.db.models.peer import peer_is_owned_min, peer_is_channel, peer_is_chat
from piltover.db.models.scheduled_task import ScheduledTask
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import Unreachable
from piltover.tl import TLObject
from piltover.tl.functions.internal import SendScheduledMessage, CreateDiscussionThread, \
    ProcessMessageToBuiltinBot, UpdateStatusForPeers, ClearDraft, SendTelegramMessage, ScheduledDeleteMessage
from piltover.tl.types.internal import TaggedBool
from piltover.worker import MessageHandler

try:
    from aiogram import Bot as AioGramBot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.exceptions import TelegramAPIError
except ImportError:
    AioGramBot = DefaultBotProperties = ParseMode = TelegramAPIError = None

handler = MessageHandler("internal")


@handler.on_request(SendScheduledMessage, ReqHandlerFlags.INTERNAL)
async def send_scheduled_message(request: SendScheduledMessage) -> TLObject:
    logger.trace("Processing scheduled message task {task_id}", task_id=request.task_id)

    async with in_transaction():
        task = await ScheduledTask.select_for_update(skip_locked=True, no_key=True).get_or_none(
            id=request.task_id,
            generation=request.generation,
            type=ScheduledTaskType.SEND_MESSAGE,
            state=ScheduledTaskState.DISPATCHING,
        ).select_related(
            "message", "message__peer", "message__peer__user", "message__content", "message__content__author",
            "message__content__media", "message__reply_to", "message__reply_to__content",
            "message__content__fwd_header", "message__content__post_info", "message__content__send_as_channel",
            "message__peer__channel",
        )

        if task is None:
            logger.warning(f"Scheduled message task {request.task_id} does not exist?")
            return TaggedBool(value=False)

        task.next_attempt_at += timedelta(minutes=5)
        task.state = ScheduledTaskState.EXECUTING
        await task.save(update_fields=["next_attempt_at", "state"])

        is_opposite = task.extra_info == b"\x01"

        scheduled = cast(MessageRef, task.message)
        content = scheduled.content
        peer = peer_ = scheduled.peer

        mentioned_users_set = set()
        if is_opposite and (peer_is_chat(peer_) or (peer_is_channel(peer_) and peer_.channel.supergroup)):
            if content.entities and content.message:
                mentioned_user_ids = await _extract_mentions_from_message(
                    content.entities, content.message, content.author_id,
                )

            if scheduled.reply_to and scheduled.reply_to.content.author_id != content.author_id:
                mentioned_user_ids.add(scheduled.content.author_id)

        messages = await scheduled.send_scheduled(is_opposite)
        await scheduled.delete()

    scheduled_by_user_id = cast(int, scheduled.scheduled_by_user_id)
    new_message = messages[0]

    await send_created_messages_internal(
        messages, is_opposite, peer, scheduled_by_user_id, False, False, mentioned_users_set,
    )

    await upd.delete_scheduled_messages(scheduled_by_user_id, peer, [scheduled.id], [new_message.id])

    return TaggedBool(value=True)


@handler.on_request(ScheduledDeleteMessage, ReqHandlerFlags.INTERNAL)
async def delete_scheduled_message(request: ScheduledDeleteMessage) -> TLObject:
    logger.trace("Deleting scheduled-for-deletion message with task {task_id}", task_id=request.task_id)

    async with in_transaction():
        task = await ScheduledTask.select_for_update(skip_locked=True, no_key=True).get_or_none(
            id=request.task_id,
            generation=request.generation,
            type=ScheduledTaskType.DELETE_MESSAGE,
            state=ScheduledTaskState.DISPATCHING,
        ).select_related("message", "message__peer", "message__peer__channel")

        if task is None:
            logger.warning(f"Scheduled message deletion task {request.task_id} does not exist?")
            return TaggedBool(value=False)

        message = cast(MessageRef, task.message)
        await MessageRef.filter(id=message.id).delete()

    if peer_is_channel(message.peer):
        await upd.delete_messages_channel(message.peer.channel, [message.id])
    elif peer_is_owned_min(message.peer):
        await upd.delete_messages(None, {message.peer.owner_id: [message.id]})
    else:
        raise Unreachable

    return TaggedBool(value=True)


@handler.on_request(CreateDiscussionThread, ReqHandlerFlags.INTERNAL)
async def create_discussion_thread(request: CreateDiscussionThread) -> TLObject:
    logger.trace("Creating discussion thread for channel message {message_id}", message_id=request.message_id)

    # TODO: forward media groups correctly: forward all grouped messages, create discussion only for the first one

    async with in_transaction():
        logger.info(f"Creating discussion thread for message {request.message_id}")
        message = await MessageRef.select_for_update().get_or_none(id=request.message_id).select_related(
            *MessageRef.PREFETCH_FIELDS, "peer__channel", "content__author", "content__send_as_channel",
        )
        if message is None or not (discussion_channel_id := message.peer.channel.discussion_id):
            return TaggedBool(value=False)

        discussion_peer = await Peer.get_or_none(
            channel_id=discussion_channel_id,
        ).select_related("channel")
        if discussion_peer is None:
            logger.warning(f"Internal channel ({discussion_channel_id}) peer does not exist")
            return TaggedBool(value=False)

        discussion_message, = await message.forward_for_peers(
            to_peer=discussion_peer,
            peers=[discussion_peer],
            fwd_header=await message.create_fwd_header(False),
            no_forwards=_resolve_noforwards(discussion_peer, None, False),
            is_forward=True,
            pinned=True,
            is_discussion=True,
        )

        logger.debug(f"Created discussion message {discussion_message.id} for message {message.id}")

        message.discussion = discussion_message
        message.content.edit_date = datetime.now(UTC)
        message.content.edit_hide = True
        message.content.version += 1
        message.content.replies_version += 1
        await message.save(update_fields=["discussion_id"])
        await message.content.save(update_fields=["edit_date", "edit_hide", "version", "replies_version"])

    await upd.send_messages_channel([discussion_message], discussion_peer.channel)
    await upd.edit_message_channel(message.peer.channel, message)

    return TaggedBool(value=True)


@handler.on_request(ProcessMessageToBuiltinBot, ReqHandlerFlags.INTERNAL)
async def process_message_to_builtin_bot(request: ProcessMessageToBuiltinBot) -> TLObject:
    logger.info(f"Processing message to bot {request.messageref_id}")
    message = await MessageRef.select_for_update().get_or_none(id=request.messageref_id).select_related(
        "peer", "peer__owner", "peer__user", "content", "content__media", "content__media__file",
    )
    if message is None:
        return TaggedBool(value=False)

    peer = message.peer

    bot_message = await bots.process_message_to_bot(peer, message)
    if bot_message is not None:
        await upd.send_message(None, [bot_message])

    return TaggedBool(value=True)


@handler.on_request(UpdateStatusForPeers, ReqHandlerFlags.INTERNAL)
async def update_status_for_peers(request: UpdateStatusForPeers) -> TLObject:
    user = await User.get(id=request.peer_owner)
    presence = await Presence.update_to_now(user)

    peer_type = PeerType(request.peer_type)

    peer_users: list[User]
    if peer_type is PeerType.USER:
        if request.peer_user == 777000:
            return TaggedBool(value=True)
        if await Peer.filter(
                owner_id=request.peer_user, user_id=request.peer_owner, blocked_at__not_isnull=True
        ).exists():
            return TaggedBool(value=True)
        peer_users = [await User.get(id=request.peer_user).only("id")]
    elif peer_type is PeerType.CHAT:
        peer_users = await User.filter(
            chatparticipants__chat_id=request.peer_chat, id__not=request.peer_owner
        ).only("id")
    else:
        return TaggedBool(value=False)

    await upd.update_status(user, presence, peer_users)
    return TaggedBool(value=True)


@handler.on_request(ClearDraft, ReqHandlerFlags.INTERNAL)
async def clear_draft(request: ClearDraft) -> TLObject:
    if await MessageDraft.filter(user_id=request.user_id, peer_id=request.peer_id).delete():
        peer: Peer = await Peer.get(id=request.peer_id)
        await upd.update_draft(request.user_id, peer, None)
        return TaggedBool(value=True)

    return TaggedBool(value=False)


@handler.on_request(SendTelegramMessage, ReqHandlerFlags.INTERNAL)
async def send_telegram_message(request: SendTelegramMessage) -> TLObject:
    if AioGramBot is None:
        logger.error("aiogram is not installed, not sending message.")
        return TaggedBool(value=False)

    if not SYSTEM_CONFIG.telegram_integration.enabled \
            or (tg_user := await TelegramUser.get_or_none(user_id=request.user_id)) is None:
        return TaggedBool(value=False)

    logger.info(f"Sending auth code to telegram user {tg_user.telegram_id}")

    async with AioGramBot(
        token=SYSTEM_CONFIG.telegram_integration.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    ) as bot:
        try:
            await bot.send_message(
                chat_id=tg_user.telegram_id,
                text=request.text,
            )
        except TelegramAPIError as e:
            logger.opt(exception=e).error("Failed to send telegram message")

    return TaggedBool(value=True)
