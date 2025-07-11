from datetime import datetime
from time import time

from loguru import logger
from pytz import UTC
from tortoise.expressions import Q
from tortoise.functions import Min

from piltover.app.utils.utils import get_perm_key
from piltover.context import request_ctx
from piltover.db.enums import UpdateType, PeerType, ChannelUpdateType, SecretUpdateType
from piltover.db.models import User, Message, UserAuthorization, State, Update, Peer, ChannelUpdate, SecretUpdate
from piltover.db.models._utils import resolve_users_chats
from piltover.exceptions import ErrorRpc
from piltover.tl import UpdateChannelTooLong
from piltover.tl.functions.updates import GetState, GetDifference, GetDifference_136, GetChannelDifference
from piltover.tl.types.updates import State as TLState, Difference, ChannelDifferenceEmpty, DifferenceEmpty, \
    ChannelDifference
from piltover.worker import MessageHandler

handler = MessageHandler("auth")


async def get_seq_qts() -> tuple[int, int]:
    ctx = request_ctx.get()
    seq_qts = await UserAuthorization.filter(
        key=await get_perm_key(ctx.auth_key_id),
    ).first().values_list("upd_seq", "upd_qts")
    if seq_qts is None:  # pragma: no cover
        logger.warning(
            f"Somehow auth is None for key {ctx.auth_key_id}, but it is in get_state_internal, "
            f"where authorization must exist ???"
        )

    return seq_qts or (0, 0)


async def get_state_internal(user: User) -> TLState:
    state = await State.get_or_none(user=user)

    seq, qts = await get_seq_qts()
    return TLState(
        pts=state.pts if state else 0,
        qts=qts,
        seq=seq,
        date=int(time()),
        unread_count=0,
    )


@handler.on_request(GetState)
async def get_state(user: User):
    return await get_state_internal(user)


@handler.on_request(GetDifference_136)
@handler.on_request(GetDifference)
async def get_difference(request: GetDifference | GetDifference_136, user: User):
    # TODO: pts_limit/qts_limit and difference slices

    requested_update = await Update.filter(user=user, pts__lte=request.pts).order_by("-pts").first()
    date = requested_update.date if requested_update is not None else datetime.fromtimestamp(request.date, UTC)

    ctx = request_ctx.get()

    last_local_secret_update = await SecretUpdate.filter(authorization__id=ctx.auth_id, qts__lte=request.qts)\
        .order_by("-qts").first()
    last_local_secret_id = last_local_secret_update.id if last_local_secret_update is not None else 0

    new = await Message.filter(
        peer__owner=user, date__gt=date
    ).select_related("author", "peer", "peer__owner", "peer__user", "peer__chat").order_by("id")
    new_updates = await Update.filter(user=user, pts__gt=request.pts).order_by("pts")
    new_secret = await SecretUpdate.filter(authorization__id=ctx.auth_id, id__gt=last_local_secret_id)

    if not new and not new_updates and not new_secret:
        return DifferenceEmpty(
            date=int(time()),
            seq=(await get_seq_qts())[0],
        )

    new_messages = {}
    new_secret_messages = []
    other_updates = []
    users_q = Q()
    chats_q = Q()
    channels_q = Q()

    for message in new:
        new_messages[message.id] = await message.to_tl(user)
        users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

    for update in new_updates:
        if update.update_type is UpdateType.MESSAGE_EDIT and update.related_id in new_messages:
            continue

        update_tl, users_q, chats_q, channels_q = await update.to_tl(user, users_q, chats_q, channels_q, ctx.auth_id)
        if update_tl is not None:
            other_updates.append(update_tl)

    for secret_update in new_secret:
        secret_update_tl = await secret_update.to_tl()
        if secret_update_tl is None:
            continue
        if secret_update.type is SecretUpdateType.NEW_MESSAGE:
            new_secret_messages.append(secret_update_tl.message)
        else:
            other_updates.append(secret_update_tl)

    channel_states = await ChannelUpdate.annotate(min_pts=Min("pts")).filter(
        channel__peers__owner=user, date__gt=date,
    ).group_by("channel__id").values_list("channel__id", "min_pts")
    for channel_id, channel_pts in channel_states:
        other_updates.append(UpdateChannelTooLong(channel_id=channel_id, pts=channel_pts))
        channels_q |= Q(id=channel_id)

    users_q |= Q(id=user.id)
    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    return Difference(
        new_messages=list(new_messages.values()),
        new_encrypted_messages=[],
        other_updates=other_updates,
        chats=[*chats.values(), *channels.values()],
        users=list(users.values()),
        state=await get_state_internal(user),
    )


@handler.on_request(GetChannelDifference)
async def get_channel_difference(request: GetChannelDifference, user: User):
    peer = await Peer.from_input_peer(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

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

    messages_from_channel_query = Q(peer__owner=user, peer_channel=peer.channel) \
                                  | Q(peer__owner=None, peer__channel=peer.channel)
    new_messages_ids = [update.related_id for update in new_updates if update.type is ChannelUpdateType.NEW_MESSAGE]
    new = await Message.filter(
        messages_from_channel_query & Q(id__in=new_messages_ids)
    ).select_related("author", "peer").order_by("id")

    new_messages = {}
    other_updates = []
    users_q = Q()
    chats_q = Q()
    channels_q = Q()

    for message in new:
        new_messages[message.id] = await message.to_tl(user)
        users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

    for update in new_updates:
        if update.type is ChannelUpdateType.EDIT_MESSAGE and update.related_id in new_messages:
            continue

        update_tl, users_q, chats_q, channels_q = await update.to_tl(user, users_q, chats_q, channels_q)
        if update_tl is not None:
            other_updates.append(update_tl)

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    return ChannelDifference(
        final=not has_more,
        pts=new_updates[-1].pts,
        timeout=30,  # TODO: what value Telegram is using?
        new_messages=list(new_messages.values()),
        other_updates=other_updates,
        chats=[*chats.values(), *channels.values()],
        users=list(users.values()),
    )
