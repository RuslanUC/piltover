from time import time

from piltover.db.enums import ChatType
from piltover.db.models import User, Update, Message
from piltover.enums import ReqHandlerFlags
from piltover.high_level import Client, MessageHandler
from piltover.tl_new import UpdateEditMessage, UpdateNewMessage
from piltover.tl_new.core_types import SerializedObject
from piltover.tl_new.functions.updates import GetState, GetDifference
from piltover.tl_new.types.updates import State, Difference

handler = MessageHandler("auth")
IGNORED_UPD = [UpdateNewMessage.tlid(), UpdateEditMessage.tlid()]


async def get_state_internal(user: User) -> State:
    last_update = await Update.filter(user=user).order_by("-pts").first()

    return State(
        pts=last_update.pts if last_update is not None else 0,
        qts=0,
        seq=1,
        date=int(time()),
        unread_count=0,
    )


# noinspection PyUnusedLocal
@handler.on_request(GetState, ReqHandlerFlags.AUTH_REQUIRED)
async def get_state(client: Client, request: GetState, user: User):
    return await get_state_internal(user)


# noinspection PyUnusedLocal
@handler.on_request(GetDifference, ReqHandlerFlags.AUTH_REQUIRED)
async def get_difference(client: Client, request: GetDifference, user: User):
    requested_update = await Update.filter(user=user, pts__lte=request.pts).order_by("-pts").first()
    date = requested_update.date if requested_update is not None else request.date

    new = await Message.filter(chat__dialogs__user=user, date__gt=date).select_related("author", "chat")
    new_messages = []
    processed_chat_ids = set()
    other_updates = []
    users = {}

    for message in new:
        chat = message.chat
        new_messages.append(await message.to_tl(user))
        if message.author.id not in users:
            users[message.author.id] = await message.author.to_tl(user)
        if chat.id not in processed_chat_ids and chat.type == ChatType.PRIVATE:
            processed_chat_ids.add(chat.id)
            if (other_user := await chat.get_other_user(user)) is not None and other_user.id not in users:
                users[other_user.id] = await other_user.to_tl(user)

    new_updates = await Update.filter(user=user, pts__lte=request.pts, update_type__not_in=IGNORED_UPD).order_by("pts")
    for update in new_updates:
        upd = SerializedObject(update.update_data)

    return Difference(
        new_messages=new_messages,
        new_encrypted_messages=[],
        other_updates=other_updates,
        chats=[],
        users=list(users.values()),
        state=await get_state_internal(user),
    )
