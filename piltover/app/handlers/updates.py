from asyncio import sleep
from datetime import datetime
from time import time
from typing import cast

from loguru import logger
from pytz import UTC
from tortoise.expressions import Q
from tortoise.functions import Min, Max

from piltover.context import request_ctx
from piltover.db.enums import UpdateType, PeerType, ChannelUpdateType, SecretUpdateType
from piltover.db.models import User, UserAuthorization, State, Update, Peer, ChannelUpdate, SecretUpdate, MessageRef
from piltover.tl import UpdateChannelTooLong
from piltover.tl.functions.updates import GetState, GetDifference, GetDifference_133, GetChannelDifference
from piltover.tl.types.updates import State as TLState, Difference, ChannelDifferenceEmpty, DifferenceEmpty, \
    ChannelDifference, DifferenceTooLong, DifferenceSlice
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("auth")

CHANNEL_UPDATES_TIMEOUT = 300  # it seems like 300 is default Telegram value


async def get_seq_qts() -> tuple[int, int]:
    ctx = request_ctx.get()
    seq_qts = await UserAuthorization.filter(
        key__id=ctx.perm_auth_key_id,
    ).first().values_list("upd_seq", "upd_qts")
    if seq_qts is None:  # pragma: no cover
        logger.warning(
            f"Somehow auth is None for key {ctx.auth_key_id} (perm {ctx.perm_auth_key_id}), "
            f"but it is in get_state_internal, where authorization must exist ???"
        )

    return seq_qts or (0, 0)


async def get_state_internal(user: User, pts: int | None = None) -> TLState:
    if pts is None:
        pts = cast(int | None, await State.get_or_none(user=user).values_list("pts", flat=True)) or 0

    seq, qts = await get_seq_qts()
    return TLState(
        pts=pts,
        qts=qts,
        seq=seq,
        date=int(time()),
        unread_count=0,
    )


@handler.on_request(GetState)
async def get_state(user: User):
    return await get_state_internal(user)


@handler.on_request(GetDifference_133)
@handler.on_request(GetDifference)
async def get_difference(request: GetDifference | GetDifference_133, user: User):
    # TODO: qts_limit

    server_pts = cast(
        int | None,
        await Update.filter(user=user).annotate(max_pts=Max("pts")).values_list("max_pts", flat=True)
    ) or 0

    if request.pts_total_limit is not None:
        if server_pts > (request.pts + request.pts_total_limit):
            return DifferenceTooLong(pts=server_pts)

    requested_update = await Update.filter(user=user, pts__lte=request.pts).order_by("-pts").first()
    date = requested_update.date if requested_update is not None else datetime.fromtimestamp(request.date, UTC)

    ctx = request_ctx.get()

    logger.trace(f"User {user.id} requested GetDifference with qts {request.qts}")

    last_local_secret_update = await SecretUpdate.filter(authorization__id=ctx.auth_id, qts__lte=request.qts)\
        .order_by("-qts").first()
    last_local_secret_id = last_local_secret_update.id if last_local_secret_update is not None else 0
    logger.trace(f"User's {user.id} last secret id is {last_local_secret_id}")

    if request.pts_limit is not None:
        max_pts = request.pts + request.pts_limit
    else:
        max_pts = server_pts

    new_updates = await Update.filter(user=user, pts__gt=request.pts, pts__lte=max_pts).order_by("pts")
    new_secret = await SecretUpdate.filter(
        authorization__id=ctx.auth_id, id__gt=last_local_secret_id
    ).select_related("message_file", "message_file__file")
    logger.trace(f"User {user.id} has {len(new_secret)} secret updates")

    new_message_ids = {
        update.related_id
        for update in new_updates
        if update.update_type is UpdateType.NEW_MESSAGE
    }
    new_messages_db = await MessageRef.filter(
        peer__owner=user, id__in=new_message_ids,
    ).select_related(*MessageRef.PREFETCH_FIELDS).order_by("id")

    if not new_messages_db and not new_updates and not new_secret:
        return DifferenceEmpty(
            date=int(time()),
            seq=(await get_seq_qts())[0],
        )

    new_messages = await MessageRef.to_tl_bulk(new_messages_db, user)
    new_secret_messages = []
    other_updates = []
    ucc = UsersChatsChannels()

    for message in new_messages_db:
        ucc.add_message(message.id)

    for update in new_updates:
        if update.update_type is UpdateType.MESSAGE_EDIT and update.related_id in new_message_ids:
            continue
        if update.update_type is UpdateType.NEW_AUTHORIZATION and (update.related_id == ctx.auth_id or ctx.layer < 163):
            continue

        update_tl = await update.to_tl(user, ctx.auth_id, ucc)
        if update_tl is not None:
            other_updates.append(update_tl)

    for idx, secret_update in enumerate(new_secret):
        if idx % 10 == 0:
            await sleep(0)
        secret_update_tl = secret_update.to_tl()
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
        # TODO: replace with UpdateChannel?
        other_updates.append(UpdateChannelTooLong(channel_id=channel_id, pts=channel_pts))
        ucc.add_channel(channel_id)

    ucc.add_user(user.id)
    users, chats, channels = await ucc.resolve()

    if max_pts >= server_pts:
        return Difference(
            new_messages=new_messages,
            new_encrypted_messages=new_secret_messages,
            other_updates=other_updates,
            chats=[*chats, *channels],
            users=users,
            state=await get_state_internal(user),
        )
    else:
        return DifferenceSlice(
            new_messages=new_messages,
            new_encrypted_messages=new_secret_messages,
            other_updates=other_updates,
            chats=[*chats, *channels],
            users=users,
            intermediate_state=await get_state_internal(user, max_pts),
        )


@handler.on_request(GetChannelDifference)
async def get_channel_difference(request: GetChannelDifference, user: User):
    # TODO: return ChannelDifferenceTooLong if request.pts + request.limit < server_pts

    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_INVALID", code=400, peer_types=(PeerType.CHANNEL,)
    )

    new_updates = await ChannelUpdate.filter(
        channel=peer.channel, pts__gt=request.pts
    ).order_by("pts").limit(request.limit)

    if not new_updates:
        return ChannelDifferenceEmpty(
            # > "always false" (as documentation says)
            # > look inside Telegram response
            # > true
            final=True,
            pts=peer.channel.pts,
            timeout=CHANNEL_UPDATES_TIMEOUT,
        )

    has_more = await ChannelUpdate.filter(channel=peer.channel, pts__gt=new_updates[-1].pts).exists()

    messages_from_channel_query = Q(peer__channel=peer.channel) & (Q(peer__owner=user) | Q(peer__owner=None))
    new_message_ids = {update.related_id for update in new_updates if update.type is ChannelUpdateType.NEW_MESSAGE}
    new = await MessageRef.filter(
        messages_from_channel_query & Q(id__in=new_message_ids)
    ).select_related(*MessageRef.PREFETCH_FIELDS).order_by("id")

    other_updates = []
    ucc = UsersChatsChannels()

    for message in new:
        ucc.add_message(message.id)

    new_messages = await MessageRef.to_tl_bulk(new, user)

    for update in new_updates:
        if update.type is ChannelUpdateType.EDIT_MESSAGE and update.related_id in new_message_ids:
            continue

        update_tl = await update.to_tl(user, ucc)
        if update_tl is not None:
            other_updates.append(update_tl)

    users, chats, channels = await ucc.resolve()

    return ChannelDifference(
        final=not has_more,
        pts=new_updates[-1].pts,
        timeout=CHANNEL_UPDATES_TIMEOUT,
        new_messages=new_messages,
        other_updates=other_updates,
        chats=[*chats, *channels],
        users=users,
    )
