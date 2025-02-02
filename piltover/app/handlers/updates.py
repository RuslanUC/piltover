from datetime import datetime
from time import time

from loguru import logger
from pytz import UTC

from piltover.app.utils.utils import get_perm_key
from piltover.context import request_ctx
from piltover.db.enums import UpdateType
from piltover.db.models import User, Message, UserAuthorization, State, UpdateV2
from piltover.tl.functions.updates import GetState, GetDifference, GetDifference_136
from piltover.tl.types.updates import State as TLState, Difference
from piltover.worker import MessageHandler

handler = MessageHandler("auth")


async def get_state_internal(user: User) -> TLState:
    ctx = request_ctx.get()
    state = await State.get_or_none(user=user)
    auth = await UserAuthorization.get_or_none(key=await get_perm_key(ctx.auth_key_id))
    if auth is None:  # pragma: no cover
        logger.warning(
            f"Somehow auth is None for key {ctx.auth_key_id}, but it is in get_state_internal, "
            f"where authorization must exist ???"
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
    ).select_related("author", "peer", "peer__owner", "peer__user", "peer__chat")
    new_messages = {}
    other_updates = []
    users = {}
    chats = {}

    for message in new:
        new_messages[message.id] = await message.to_tl(user)
        await message.tl_users_chats(user, users, chats)

    new_updates = await UpdateV2.filter(user=user, pts__gt=request.pts).order_by("pts")
    for update in new_updates:
        if update.update_type == UpdateType.MESSAGE_EDIT and update.related_id in new_messages:
            continue

        other_updates.append(await update.to_tl(user, users, chats))

    if user.id not in users:
        users[user.id] = await user.to_tl(user)

    return Difference(
        new_messages=list(new_messages.values()),
        new_encrypted_messages=[],
        other_updates=other_updates,
        chats=list(chats.values()),
        users=list(users.values()),
        state=await get_state_internal(user),
    )
