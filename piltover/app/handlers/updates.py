from datetime import datetime
from time import time

from loguru import logger
from pytz import UTC
from tortoise.expressions import Q

from piltover.app.utils.utils import get_perm_key
from piltover.context import request_ctx
from piltover.db.enums import UpdateType, PeerType, ChannelUpdateType
from piltover.db.models import User, Message, UserAuthorization, State, Update, Peer
from piltover.db.models.channel_update import ChannelUpdate
from piltover.exceptions import ErrorRpc
from piltover.tl.functions.updates import GetState, GetDifference, GetDifference_136, GetChannelDifference
from piltover.tl.types.updates import State as TLState, Difference, ChannelDifferenceEmpty, DifferenceEmpty, \
    ChannelDifference
from piltover.worker import MessageHandler

handler = MessageHandler("auth")


async def get_seq() -> int:
    ctx = request_ctx.get()
    # TODO: get only "upd_seq" field instead of whole model
    auth = await UserAuthorization.get_or_none(key=await get_perm_key(ctx.auth_key_id))
    if auth is None:  # pragma: no cover
        logger.warning(
            f"Somehow auth is None for key {ctx.auth_key_id}, but it is in get_state_internal, "
            f"where authorization must exist ???"
        )

    return auth.upd_seq if auth is not None else 0


async def get_state_internal(user: User) -> TLState:
    state = await State.get_or_none(user=user)

    return TLState(
        pts=state.pts if state else 0,
        qts=0,
        seq=await get_seq(),
        date=int(time()),
        unread_count=0,
    )


@handler.on_request(GetState)
async def get_state(user: User):
    return await get_state_internal(user)


@handler.on_request(GetDifference_136)
@handler.on_request(GetDifference)
async def get_difference(request: GetDifference | GetDifference_136, user: User):
    requested_update = await Update.filter(user=user, pts__lte=request.pts).order_by("-pts").first()
    date = requested_update.date if requested_update is not None else datetime.fromtimestamp(request.date, UTC)

    new = await Message.filter(
        peer__owner=user, date__gt=date
    ).select_related("author", "peer", "peer__owner", "peer__user", "peer__chat").order_by("id")
    new_updates = await Update.filter(user=user, pts__gt=request.pts).order_by("pts")

    if not new and not new_updates:
        return DifferenceEmpty(
            date=int(time()),
            seq=await get_seq(),
        )

    new_messages = {}
    other_updates = []
    users = {}
    chats = {}
    channels = {}

    for message in new:
        new_messages[message.id] = await message.to_tl(user)
        await message.tl_users_chats(user, users, chats, channels)

    for update in new_updates:
        if update.update_type is UpdateType.MESSAGE_EDIT and update.related_id in new_messages:
            continue

        if (update_tl := await update.to_tl(user, users, chats, channels)) is not None:
            other_updates.append(update_tl)

    if user.id not in users:
        users[user.id] = await user.to_tl(user)

    return Difference(
        new_messages=list(new_messages.values()),
        new_encrypted_messages=[],
        other_updates=other_updates,
        chats=[*chats.values(), *channels.values()],
        users=list(users.values()),
        state=await get_state_internal(user),
    )


@handler.on_request(GetChannelDifference)
async def get_difference(request: GetChannelDifference, user: User):
    peer = await Peer.from_input_peer(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    messages_from_channel_query = Q(peer__owner=user, peer_channel=peer.channel) \
                                  | Q(peer__owner=None, peer__channel=peer.channel)
    new_updates = await ChannelUpdate.filter(
        channel=peer.channel, pts__gt=request.pts
    ).order_by("pts").limit(request.limit)

    if not new_updates:
        return ChannelDifferenceEmpty(
            final=False,
            pts=peer.channel.pts,
            timeout=30,  # TODO: what value Telegram is using?
        )

    has_more = await ChannelUpdate.filter(channel=peer.channel, pts__gt=new_updates[-1].pts).exists()

    new_messages_ids = [update.related_id for update in new_updates if update.type is ChannelUpdateType.NEW_MESSAGE]
    new = await Message.filter(
        messages_from_channel_query & Q(id__in=new_messages_ids)
    ).select_related("author", "peer").order_by("id")

    new_messages = {}
    other_updates = []
    users = {}
    chats = {}
    channels = {}

    for message in new:
        new_messages[message.id] = await message.to_tl(user)
        await message.tl_users_chats(user, users, chats, channels)

    for update in new_updates:
        if update.type is ChannelUpdateType.EDIT_MESSAGE and update.related_id in new_messages:
            continue

        if (update_tl := await update.to_tl(user, users, chats, channels)) is not None:
            other_updates.append(update_tl)

    return ChannelDifference(
        final=not has_more,
        pts=new_updates[-1].pts,
        timeout=30,  # TODO: what value Telegram is using?
        new_messages=list(new_messages.values()),
        other_updates=other_updates,
        chats=[*chats.values(), *channels.values()],
        users=list(users.values()),
    )
