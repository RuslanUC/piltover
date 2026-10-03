from time import time
from typing import cast

from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages import sending
from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import ScheduledTaskType, ScheduledTaskState
from piltover.db.models import Peer, MessageRef, MessageContent, ScheduledTask, peer_is_chat, peer_is_channel
from piltover.enums import ReqHandlerFlags
from piltover.tl import Updates
from piltover.tl.functions.messages import GetScheduledHistory, GetScheduledMessages, SendScheduledMessages, \
    DeleteScheduledMessages
from piltover.tl.types.messages import Messages, MessagesNotModified
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("messages.scheduled")


async def _format_messages(user_id: int, messages: list[MessageRef]) -> Messages:
    messages_tl = await MessageRef.to_tl_bulk_maybecached(messages, user_id)

    ucc = UsersChatsChannels()
    for message_tl in messages_tl:
        ucc.add_from_tl(message_tl)

    users, chats, channels = await ucc.resolve()

    return Messages(
        messages=messages_tl,
        chats=[*chats, *channels],
        users=users,
    )


@handler.on_request(GetScheduledHistory, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_scheduled_history(request: GetScheduledHistory, user_id: int) -> Messages | MessagesNotModified:
    peer = await Peer.from_input_peer_raise(user_id, request.peer)

    message_ids = await MessageRef.filter(
        peer=peer, scheduled_by_user_id=user_id,
    ).order_by("content__scheduled_date").values_list("id", flat=True)
    messages_hash = telegram_hash(cast(list[int], message_ids), 64)

    if messages_hash == request.hash:
        return MessagesNotModified(count=len(message_ids))

    messages = await MessageRef.filter(id__in=message_ids).order_by("content__scheduled_date").select_related(
        *MessageRef.PREFETCH_MAYBECACHED
    )

    return await _format_messages(user_id, messages)


@handler.on_request(GetScheduledMessages, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_scheduled_messages(request: GetScheduledMessages, user_id: int) -> Messages:
    peer = await Peer.from_input_peer_raise(user_id, request.peer)

    messages = await MessageRef.filter(
        peer=peer, scheduled_by_user_id=user_id, id__in=request.id,
    ).order_by("content__scheduled_date").select_related(*MessageRef.PREFETCH_MAYBECACHED)

    return await _format_messages(user_id, messages)


@handler.on_request(SendScheduledMessages, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def send_scheduled_messages(request: SendScheduledMessages, user_id: int) -> Updates:
    peer = await Peer.from_input_peer_raise(user_id, request.peer)

    updates = Updates(updates=[], chats=[], users=[], date=int(time()), seq=0)
    deleted = []
    new = []

    async with in_transaction():
        tasks = await ScheduledTask.select_for_update(skip_locked=True, no_key=True).filter(
            message_id__in=request.id[:100],
            type=ScheduledTaskType.SEND_MESSAGE,
            state=ScheduledTaskState.SCHEDULED,
        ).select_related(
            "message", "message__peer", "message__peer__user", "message__content", "message__content__author",
            "message__content__media", "message__reply_to", "message__reply_to__content",
            "message__content__fwd_header", "message__content__post_info", "message__content__send_as_channel",
            "message__peer__channel",
        )

        # TODO: do in bulk

        for task in tasks:
            scheduled = cast(MessageRef, task.message)
            content = scheduled.content
            peer_ = scheduled.peer
            is_opposite = task.extra_info == b"\x01"

            mentioned_users_set = set()
            if is_opposite and (peer_is_chat(peer_) or (peer_is_channel(peer_) and peer_.channel.supergroup)):
                if content.entities and content.message:
                    mentioned_user_ids = await sending._extract_mentions_from_message(
                        content.entities, content.message, content.author_id,
                    )

                if scheduled.reply_to and scheduled.reply_to.content.author_id != content.author_id:
                    mentioned_user_ids.add(scheduled.content.author_id)

            messages = await scheduled.send_scheduled(is_opposite)
            msg_updates = await sending.send_created_messages_internal(
                messages, is_opposite, scheduled.peer, user_id, False, False, mentioned_users_set,
            )
            await scheduled.content.delete()

            updates.updates.extend(msg_updates.updates)
            updates.chats.extend(msg_updates.chats)
            updates.users.extend(msg_updates.users)
            updates.date = msg_updates.date

            new.append(messages[0].id)
            deleted.append(scheduled.id)

    if deleted and new:
        delete_updates = await upd.delete_scheduled_messages(user_id, peer, deleted, new)
        updates.updates.extend(delete_updates.updates)

    return updates


@handler.on_request(DeleteScheduledMessages, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def delete_scheduled_messages(request: DeleteScheduledMessages, user_id: int) -> Updates:
    peer = await Peer.from_input_peer_raise(user_id, request.peer)
    messages = await MessageRef.filter(
        peer=peer, id__in=request.id, scheduled_by_user_id=user_id,
    ).values_list("id", "content_id")

    ids = []
    content_ids = []
    for ref_id, content_id in messages:
        ids.append(ref_id)
        content_ids.append(content_id)

    await MessageContent.filter(id__in=content_ids).delete()

    return await upd.delete_scheduled_messages(user_id, peer, ids)
