from time import time

from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages import sending
from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import MessageType, PeerType
from piltover.db.models import User, Peer, MessageRef, MessageContent
from piltover.enums import ReqHandlerFlags
from piltover.tl import Updates
from piltover.tl.functions.messages import GetScheduledHistory, GetScheduledMessages, SendScheduledMessages, \
    DeleteScheduledMessages
from piltover.tl.types.messages import Messages, MessagesNotModified
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("messages.scheduled")


async def _format_messages(user: User, messages: list[MessageRef]) -> Messages:
    ucc = UsersChatsChannels()

    for message in messages:
        ucc.add_message(message.content_id)

    messages_tl = await MessageRef.to_tl_bulk(messages, user)
    users, chats, channels = await ucc.resolve()

    return Messages(
        messages=messages_tl,
        chats=[*chats, *channels],
        users=users,
    )


@handler.on_request(GetScheduledHistory, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_scheduled_history(request: GetScheduledHistory, user: User) -> Messages | MessagesNotModified:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    message_ids = await MessageRef.filter(
        peer=peer, content__type=MessageType.SCHEDULED,
    ).order_by("content__scheduled_date").values_list("id", flat=True)
    messages_hash = telegram_hash(message_ids, 64)

    if messages_hash == request.hash:
        return MessagesNotModified(count=len(message_ids))

    messages = await MessageRef.filter(id__in=message_ids).order_by("content__scheduled_date").select_related(
        *MessageRef.PREFETCH_FIELDS
    )

    return await _format_messages(user, messages)


@handler.on_request(GetScheduledMessages, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_scheduled_messages(request: GetScheduledMessages, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    messages = await MessageRef.filter(
        peer=peer, content__type=MessageType.SCHEDULED, id__in=request.id,
    ).order_by("content__scheduled_date").select_related(*MessageRef.PREFETCH_FIELDS)

    return await _format_messages(user, messages)


@handler.on_request(SendScheduledMessages, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def send_scheduled_messages(request: SendScheduledMessages, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    updates = Updates(updates=[], chats=[], users=[], date=int(time()), seq=0)
    deleted = []
    new = []

    async with in_transaction():
        scheduled_messages = await MessageRef.select_for_update(
            skip_locked=True, no_key=True,
        ).get_or_none(
            peer=peer, id__in=request.id[:100],
        ).select_related(
            "taskiqscheduledmessages", "peer", "peer__owner", "peer__user", "content", "content__author",
            "content__media", "content__reply_to", "content__fwd_header", "content__post_info",
        )

        for scheduled in scheduled_messages:
            task = scheduled.taskiqscheduledmessages
            messages = await scheduled.send_scheduled(task.opposite)
            msg_updates = await sending.send_created_messages_internal(
                messages, task.opposite, scheduled.peer, scheduled.peer.owner, False, task.mentioned_users_set,
            )
            await scheduled.content.delete()

            updates.updates.extend(msg_updates.updates)
            updates.chats.extend(msg_updates.chats)
            updates.users.extend(msg_updates.users)
            updates.date = msg_updates.date

            if peer.type is PeerType.CHANNEL and task.opposite:
                new_message = next(iter(messages.values()))
            else:
                new_message = messages[peer]

            new.append(new_message.id)
            deleted.append(scheduled.id)

    if deleted and new:
        delete_updates = await upd.delete_scheduled_messages(user, peer, deleted, new)
        updates.updates.extend(delete_updates.updates)

    return updates


@handler.on_request(DeleteScheduledMessages, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def delete_scheduled_messages(request: DeleteScheduledMessages, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    messages = await MessageRef.filter(
        peer=peer, id__in=request.id, content__type=MessageType.SCHEDULED,
    ).values_list("id", "content_id")

    ids = []
    content_ids = []
    for ref_id, content_id in messages:
        ids.append(ref_id)
        content_ids.append(content_id)

    await MessageContent.filter(id__in=content_ids).delete()

    return await upd.delete_scheduled_messages(user, peer, ids)
