from time import time

from tortoise.expressions import Q

from piltover.app.handlers.messages import sending
from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import MessageType
from piltover.db.models import User, Peer, Message, TaskIqScheduledMessage
from piltover.db.models._utils import resolve_users_chats
from piltover.tl import Updates
from piltover.tl.functions.messages import GetScheduledHistory, GetScheduledMessages, SendScheduledMessages
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
    # TODO: use transactions

    peer = await Peer.from_input_peer_raise(user, request.peer)
    tasks = await TaskIqScheduledMessage.filter(message__peer=peer, message__id__in=request.id[:100]).select_related(
        "message", "message__peer", "message__peer__owner", "message__author", "message__media",
        "message__reply_to", "message__fwd_header", "message__post_info",
    )

    updates = Updates(updates=[], chats=[], users=[], date=int(time()), seq=0)

    for task in tasks:
        scheduled = task.message
        messages = await scheduled.send_scheduled(task.opposite)
        msg_updates = await sending.send_created_messages_internal(
            messages, task.opposite, scheduled.peer, scheduled.peer.owner, False, task.mentioned_users_set,
        )
        await scheduled.delete()

        updates.updates.extend(msg_updates.updates)
        updates.chats.extend(msg_updates.chats)
        updates.users.extend(msg_updates.users)
        updates.date = msg_updates.date

    return updates


# TODO:
#  messages.deleteScheduledMessages#59ae2b16 peer:InputPeer id:Vector<int> = Updates;
