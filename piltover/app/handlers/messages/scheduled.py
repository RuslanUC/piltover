from time import time

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages import sending
from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import MessageType, PeerType
from piltover.db.models import User, Peer, Message
from piltover.db.models._utils import resolve_users_chats
from piltover.tl import Updates
from piltover.tl.functions.messages import GetScheduledHistory, GetScheduledMessages, SendScheduledMessages, \
    DeleteScheduledMessages
from piltover.tl.types.messages import Messages, MessagesNotModified
from piltover.worker import MessageHandler

handler = MessageHandler("messages.scheduled")


async def _format_messages(user: User, messages: list[Message]) -> Messages:
    users_q = Q()
    chats_q = Q()
    channels_q = Q()

    messages_tl = []
    for message in messages:
        messages_tl.append(await message.to_tl(user))
        users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})
    chats_tl = [*chats.values(), *channels.values()]
    users_tl = list(users.values())

    return Messages(
        messages=messages_tl,
        chats=chats_tl,
        users=users_tl,
    )


@handler.on_request(GetScheduledHistory)
async def get_scheduled_history(request: GetScheduledHistory, user: User) -> Messages | MessagesNotModified:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    message_ids = await Message.filter(
        peer=peer, type=MessageType.SCHEDULED,
    ).order_by("scheduled_date").values_list("id", flat=True)
    messages_hash = telegram_hash(message_ids, 64)

    if messages_hash == request.hash:
        return MessagesNotModified(count=len(message_ids))

    messages = await Message.filter(id__in=message_ids).order_by("scheduled_date").select_related(
        "peer", "peer__user", "author", "media",
    )

    return await _format_messages(user, messages)


@handler.on_request(GetScheduledMessages)
async def get_scheduled_messages(request: GetScheduledMessages, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    messages = await Message.filter(
        peer=peer, type=MessageType.SCHEDULED, id__in=request.id,
    ).order_by("scheduled_date").select_related("peer", "peer__user", "author", "media")

    return await _format_messages(user, messages)


@handler.on_request(SendScheduledMessages)
async def send_scheduled_messages(request: SendScheduledMessages, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    updates = Updates(updates=[], chats=[], users=[], date=int(time()), seq=0)
    deleted = []
    new = []

    async with in_transaction():
        scheduled_messages = await Message.select_for_update(
            skip_locked=True, no_key=True,
        ).get_or_none(
            peer=peer, id__in=request.id[:100],
        ).select_related(
            "taskiqscheduledmessages", "peer", "peer__owner", "peer__user", "author", "media", "reply_to",
            "fwd_header", "post_info",
        )

        for scheduled in scheduled_messages:
            task = scheduled.taskiqscheduledmessages
            messages = await scheduled.send_scheduled(task.opposite)
            msg_updates = await sending.send_created_messages_internal(
                messages, task.opposite, scheduled.peer, scheduled.peer.owner, False, task.mentioned_users_set,
            )
            await scheduled.delete()

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


@handler.on_request(DeleteScheduledMessages)
async def delete_scheduled_messages(request: DeleteScheduledMessages, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    ids_to_delete = await Message.filter(
        peer=peer, id__in=request.id, type=MessageType.SCHEDULED,
    ).values_list("id", flat=True)

    await Message.filter(id__in=ids_to_delete).delete()

    return await upd.delete_scheduled_messages(user, peer, ids_to_delete)
