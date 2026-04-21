from collections import defaultdict
from datetime import datetime, UTC

from loguru import logger
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers import bots
from piltover.app.handlers.messages.sending import send_created_messages_internal, _resolve_noforwards
from piltover.db.enums import PeerType
from piltover.db.models import Peer, MessageRef, MessageContent, User, Presence, MessageDraft
from piltover.enums import ReqHandlerFlags
from piltover.tl import TLObject
from piltover.tl.functions.internal import SendScheduledMessage, DeleteScheduledMessage, CreateDiscussionThread, \
    ProcessMessageToBuiltinBot, UpdateStatusForPeers, ClearDraft
from piltover.tl.types.internal import TaggedBool
from piltover.worker import MessageHandler

handler = MessageHandler("internal")


@handler.on_request(SendScheduledMessage, ReqHandlerFlags.INTERNAL)
async def send_scheduled_message(request: SendScheduledMessage) -> TLObject:
    logger.trace("Processing scheduled message {message_id}", message_id=request.message_id)

    async with in_transaction():
        scheduled = await MessageRef.select_for_update(
            skip_locked=True, no_key=True,
        ).get_or_none(
            id=request.message_id,
        ).select_related(
            "taskiqscheduledmessages", "peer", "peer__owner", "peer__user", "content", "content__author",
            "content__media", "reply_to", "content__fwd_header", "content__post_info", "content__send_as_channel",
        )
        if scheduled is None:
            logger.warning(f"Scheduled message {request.message_id} does not exist?")
            return TaggedBool(value=False)

        task = scheduled.taskiqscheduledmessages

        messages = await scheduled.send_scheduled(task.opposite)
        await scheduled.delete()

    await send_created_messages_internal(
        messages, task.opposite, scheduled.peer, scheduled.peer.owner, False, task.mentioned_users_set,
    )

    peer = scheduled.peer
    if peer.type is PeerType.CHANNEL and task.opposite:
        new_message = next(iter(messages.values()))
    else:
        new_message = messages[peer]

    await upd.delete_scheduled_messages(peer.owner, peer, [scheduled.id], [new_message.id])

    return TaggedBool(value=True)


@handler.on_request(DeleteScheduledMessage, ReqHandlerFlags.INTERNAL)
async def delete_scheduled_message(request: DeleteScheduledMessage) -> TLObject:
    logger.trace("Deleting scheduled-for-deletion message {message_id}", message_id=request.message_id)

    async with in_transaction():
        to_delete = await MessageRef.select_for_update(
            skip_locked=True, no_key=True,
        ).filter(content_id=request.message_id).select_related("peer", "peer__owner", "peer__channel")

        all_ids = []
        regular_messages = defaultdict(list)
        channel_messages = defaultdict(list)

        for message in to_delete:
            all_ids.append(message.id)
            if message.peer.type is PeerType.CHANNEL:
                channel_messages[message.peer.channel_id].append(message.id)
            else:
                regular_messages[message.peer.owner].append(message.id)

        await MessageContent.filter(id=request.message_id).delete()

        if regular_messages:
            await upd.delete_messages(None, regular_messages)
        for channel, message_ids in channel_messages.items():
            await upd.delete_messages_channel(channel, message_ids)

    return TaggedBool(value=True)


@handler.on_request(CreateDiscussionThread, ReqHandlerFlags.INTERNAL)
async def create_discussion_thread(request: CreateDiscussionThread) -> TLObject:
    logger.trace("Creating discussion thread for channel message {message_id}", message_id=request.message_id)

    # TODO: forward media groups correctly

    async with in_transaction():
        logger.info(f"Creating discussion thread for message {request.message_id}")
        message = await MessageRef.select_for_update().get_or_none(id=request.message_id).select_related(
            *MessageRef.PREFETCH_FIELDS, "peer__channel", "content__send_as_channel",
        )
        if message is None or not message.peer.channel.discussion_id:
            return TaggedBool(value=False)

        discussion_peer = await Peer.get_or_none(
            owner=None, channel_id=message.peer.channel.discussion_id,
        ).select_related("channel")

        discussion_message, = await message.forward_for_peers(
            to_peer=discussion_peer,
            peers=[discussion_peer],
            no_forwards=_resolve_noforwards(discussion_peer, None, False),
            fwd_header=await message.create_fwd_header(False),
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
        await upd.send_message(None, {peer: bot_message})

    return TaggedBool(value=True)


@handler.on_request(UpdateStatusForPeers, ReqHandlerFlags.INTERNAL)
async def update_status_for_peers(request: UpdateStatusForPeers) -> TLObject:
    user = await User.get(id=request.peer_owner)
    presence = await Presence.update_to_now(user)

    peer_type = PeerType(request.peer_type)

    if peer_type is PeerType.USER:
        if request.peer_user == 777000:
            return TaggedBool(value=True)
        if await Peer.filter(
                owner_id=request.peer_user, user_id=request.peer_owner, blocked_at__not_isnull=True
        ).exists():
            return TaggedBool(value=True)
        peers = [await User.get(id=request.peer_user).only("id")]
    elif peer_type is PeerType.CHAT:
        peers = await User.filter(chatparticipants__chat_id=request.peer_chat, id__not=request.peer_owner).only("id")
    else:
        return TaggedBool(value=False)

    await upd.update_status(user, presence, peers)
    return TaggedBool(value=True)


@handler.on_request(ClearDraft, ReqHandlerFlags.INTERNAL)
async def clear_draft(request: ClearDraft) -> TLObject:
    if (draft := await MessageDraft.get_or_none(peer_id=request.peer_id).only("id")) is not None:
        peer = await Peer.get(id=request.peer_id)
        await draft.delete()
        await upd.update_draft(peer.owner_id, peer, None)
        return TaggedBool(value=True)

    return TaggedBool(value=False)
