from datetime import datetime
from time import time

from loguru import logger
from pytz import UTC

from piltover.app.utils.utils import get_perm_key
from piltover.context import request_ctx
from piltover.db.enums import UpdateType, PeerType
from piltover.db.models import User, Message, UserAuthorization, State, UpdateV2
from piltover.worker import MessageHandler
from piltover.tl import UpdateNewMessage, UpdateShortMessage
from piltover.tl.functions.updates import GetState, GetDifference, GetDifference_136
from piltover.tl.types.updates import State as TLState, Difference

handler = MessageHandler("auth")
IGNORED_UPD = [UpdateNewMessage.tlid(), UpdateShortMessage.tlid()]


async def get_state_internal(user: User) -> TLState:
    ctx = request_ctx.get()
    state = await State.get_or_none(user=user)
    auth = await UserAuthorization.get_or_none(key=await get_perm_key(ctx.auth_key_id))
    if auth is None:
        logger.warning(
            "Somehow auth is None for key {ctx.auth_key_id}, but it is in get_state_internal, "
            "where authorization must exist ???"
        )

    return TLState(
        pts=state.pts if state else 0,
        qts=0,
        seq=auth.upd_seq if auth is not None else 0,
        date=int(time()),
        unread_count=0,
    )


@handler.on_request(GetState)
async def get_state(user: User):
    return await get_state_internal(user)


@handler.on_request(GetDifference_136)
@handler.on_request(GetDifference)
async def get_difference(request: GetDifference | GetDifference_136, user: User):
    requested_update = await UpdateV2.filter(user=user, pts__lte=request.pts).order_by("-pts").first()
    date = requested_update.date if requested_update is not None else datetime.fromtimestamp(request.date, UTC)

    new = await Message.filter(
        peer__owner=user, date__gt=date
    ).select_related("author", "peer", "peer__owner", "peer__user")
    new_messages = {}
    processed_peer_ids = set()
    other_updates = []
    users = {}
    chats = {}

    for message in new:
        peer = message.peer

        new_messages[message.id] = await message.to_tl(user)
        if message.author.id not in users:
            users[message.author.id] = await message.author.to_tl(user)
        if message.peer.type is PeerType.CHAT and message.peer.chat_id not in chats:
            await message.peer.fetch_related("chat")
            chats[message.peer.chat.id] = await message.peer.chat.to_tl(user)

        if peer.id not in processed_peer_ids:
            processed_peer_ids.add(peer.id)
            for other_peer in await peer.get_opposite():
                if other_peer.user_id is not None and other_peer.user_id not in users:
                    await other_peer.fetch_related("user")
                    users[other_peer.user.id] = await other_peer.user.to_tl(user)

    new_updates = await UpdateV2.filter(user=user, pts__gt=request.pts).order_by("pts")
    for update in new_updates:
        if update.update_type == UpdateType.MESSAGE_EDIT and update.related_id in new_messages:
            continue

        other_updates.append(await update.to_tl(user, users, chats))

    if user.id not in users:
        users[user.id] = await user.to_tl(user)

    # noinspection PyTypeChecker
    return Difference(
        new_messages=list(new_messages.values()),
        new_encrypted_messages=[],
        other_updates=other_updates,
        chats=list(chats.values()),
        users=list(users.values()),
        state=await get_state_internal(user),
    )
