from datetime import datetime
from time import time

from piltover.db.enums import ChatType, UpdateType
from piltover.db.models import User, Message, UserAuthorization, State, UpdateV2
from piltover.enums import ReqHandlerFlags
from piltover.high_level import Client, MessageHandler
from piltover.tl import UpdateNewMessage, UpdateShortMessage
from piltover.tl.functions.updates import GetState, GetDifference, GetDifference_136
from piltover.tl.types.updates import State as TLState, Difference

handler = MessageHandler("auth")
IGNORED_UPD = [UpdateNewMessage.tlid(), UpdateShortMessage.tlid()]


async def get_state_internal(client: Client, user: User) -> TLState:
    state = await State.get_or_none(user=user)
    auth = await UserAuthorization.get(key__id=str(await client.auth_data.get_perm_id()))

    return TLState(
        pts=state.pts if state else 0,
        qts=0,
        seq=auth.upd_seq,
        date=int(time()),
        unread_count=0,
    )


# noinspection PyUnusedLocal
@handler.on_request(GetState, ReqHandlerFlags.AUTH_REQUIRED)
async def get_state(client: Client, request: GetState, user: User):
    return await get_state_internal(client, user)


# noinspection PyUnusedLocal
@handler.on_request(GetDifference_136, ReqHandlerFlags.AUTH_REQUIRED)
@handler.on_request(GetDifference, ReqHandlerFlags.AUTH_REQUIRED)
async def get_difference(client: Client, request: GetDifference | GetDifference_136, user: User):
    requested_update = await UpdateV2.filter(user=user, pts__lte=request.pts).order_by("-pts").first()
    date = requested_update.date if requested_update is not None else request.date
    date = datetime.fromtimestamp(date)

    new = await Message.filter(chat__dialogs__user=user, date__gt=date).select_related("author", "chat")
    new_messages = {}
    processed_chat_ids = set()
    other_updates = []
    users = {}

    for message in new:
        chat = message.chat
        new_messages[message.id] = await message.to_tl(user)
        if message.author.id not in users:
            users[message.author.id] = await message.author.to_tl(user)
        if chat.id not in processed_chat_ids and chat.type == ChatType.PRIVATE:
            processed_chat_ids.add(chat.id)
            if (other_user := await chat.get_other_user(user)) is not None and other_user.id not in users:
                users[other_user.id] = await other_user.to_tl(user)

    new_updates = await UpdateV2.filter(user=user, pts__gt=request.pts).order_by("pts")
    for update in new_updates:
        if update.update_type == UpdateType.MESSAGE_EDIT and update.related_id in new_messages:
            continue

        other_updates.append(await update.to_tl(user, users))

    if user.id not in users:
        users[user.id] = await user.to_tl(user)

    # noinspection PyTypeChecker
    return Difference(
        new_messages=list(new_messages.values()),
        new_encrypted_messages=[],
        other_updates=other_updates,
        chats=[],
        users=list(users.values()),
        state=await get_state_internal(client, user),
    )
