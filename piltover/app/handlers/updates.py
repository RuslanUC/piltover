from asyncio import sleep
from datetime import datetime, UTC
from time import time
from typing import cast

from loguru import logger
from tortoise.functions import Min, Max

from piltover.context import request_ctx
from piltover.db.enums import UpdateType, PeerType, ChannelUpdateType, SecretUpdateType
from piltover.db.models import UserAuthorization, State, Update, Peer, ChannelUpdate, SecretUpdate, MessageRef, Dialog
from piltover.enums import ReqHandlerFlags
from piltover.tl import UpdateChannelTooLong
from piltover.tl.functions.updates import GetState, GetDifference, GetDifference_133, GetChannelDifference
from piltover.tl.types.updates import State as TLState, Difference, ChannelDifferenceEmpty, DifferenceEmpty, \
    ChannelDifference, DifferenceTooLong, DifferenceSlice, ChannelDifferenceTooLong
from piltover.tl.base.updates import Difference as TLDifferenceBase, ChannelDifference as TLChannelDifferenceBase
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("auth")

# Default telegram value is 30
CHANNEL_UPDATES_TIMEOUT = 10


async def get_seq_qts() -> tuple[int, int]:
    ctx = request_ctx.get()
    seq_qts = await UserAuthorization.filter(
        key_id=ctx.perm_auth_key_id,
    ).first().values_list("upd_seq", "upd_qts")
    if seq_qts is None:  # pragma: no cover
        logger.warning(
            f"Somehow auth is None for key {ctx.auth_key_id} (perm {ctx.perm_auth_key_id}), "
            f"but it is in get_state_internal, where authorization must exist ???"
        )

    return seq_qts or (0, 0)


async def get_state_internal(user_id: int, pts: int | None = None) -> TLState:
    if pts is None:
        pts = cast(int | None, await State.get_or_none(user_id=user_id).values_list("pts", flat=True)) or 0

    seq, qts = await get_seq_qts()
    return TLState(
        pts=pts,
        qts=qts,
        seq=seq,
        date=int(time()),
        unread_count=0,
    )


@handler.on_request(GetState, ReqHandlerFlags.DONT_FETCH_USER)
async def get_state(user_id: int):
    return await get_state_internal(user_id)


@handler.on_request(GetDifference_133, ReqHandlerFlags.DONT_FETCH_USER)
@handler.on_request(GetDifference, ReqHandlerFlags.DONT_FETCH_USER)
async def get_difference(request: GetDifference | GetDifference_133, user_id: int) -> TLDifferenceBase:
    # TODO: qts_limit

    server_pts = cast(
        int | None,
        await Update.filter(user_id=user_id).annotate(max_pts=Max("pts")).first().values_list("max_pts", flat=True)
    ) or 0

    if request.pts_total_limit is not None:
        if server_pts > (request.pts + request.pts_total_limit):
            return DifferenceTooLong(pts=server_pts)

    requested_update = await Update.filter(user_id=user_id, pts__lte=request.pts).order_by("-pts").first()
    date = requested_update.date if requested_update is not None else datetime.fromtimestamp(request.date, UTC)

    ctx = request_ctx.get()

    logger.trace(f"User {user_id} requested GetDifference with qts {request.qts}")

    last_local_secret_update = await SecretUpdate.filter(authorization_id=ctx.auth_id, qts__lte=request.qts)\
        .order_by("-qts").first()
    last_local_secret_id = last_local_secret_update.id if last_local_secret_update is not None else 0
    logger.trace(f"User's {user_id} last secret id is {last_local_secret_id}")

    if isinstance(request, GetDifference) and request.pts_limit is not None:
        max_pts = request.pts + request.pts_limit
    else:
        max_pts = server_pts

    logger.trace(f"Getting updates for user {user_id} from pts {request.pts} to pts {max_pts}")

    # NOTE: telegram forces slicing at 2500 pts, we do it at 500 pts just to be safe
    new_updates = await Update.filter(
        user_id=user_id, pts__gt=request.pts, pts__lte=max_pts,
    ).order_by("pts").limit(500).select_related(
        "peer", "dialog", "draft", "encrypted_chat", "authorization", "stickerset",
        *Update.MESSAGE_PREFETCH_MAYBECACHED,
    )
    new_secret = await SecretUpdate.filter(
        authorization_id=ctx.auth_id, id__gt=last_local_secret_id
    ).select_related("message_file", "message_file__file")
    logger.trace(f"User {user_id} has {len(new_secret)} secret updates")

    new_message_ids = {
        update.message_id
        for update in new_updates
        if update.update_type is UpdateType.NEW_MESSAGE
    }
    all_messages_to_format = [update.message for update in new_updates if update.message is not None]
    all_messages = {
        message.id: message
        for message in await MessageRef.to_tl_bulk_maybecached(all_messages_to_format, user_id)
    }

    if not new_updates and not new_secret:
        return DifferenceEmpty(
            date=int(time()),
            seq=(await get_seq_qts())[0],
        )

    new_messages = [
        all_messages[update.message_id]
        for update in new_updates
        if update.update_type is UpdateType.NEW_MESSAGE and update.message is not None
    ]
    new_secret_messages = []
    other_updates = []
    ucc = UsersChatsChannels()

    for update in new_updates:
        if update.update_type is UpdateType.NEW_MESSAGE and update.message is not None:
            ucc.add_message(update.message.content_id)

    for update in new_updates:
        if update.update_type is UpdateType.MESSAGE_EDIT and update.message_id in new_message_ids:
            continue
        if update.update_type is UpdateType.NEW_AUTHORIZATION and (update.related_id == ctx.auth_id or ctx.layer < 163):
            continue

        update_tl = await update.to_tl(user_id, all_messages, ctx.auth_id, ucc)
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
        channel__chatparticipants__user_id=user_id, channel__chatparticipants__left=False, date__gt=date,
    ).group_by("channel_id").values_list("channel_id", "min_pts")
    for channel_id, channel_pts in channel_states:
        other_updates.append(UpdateChannelTooLong(channel_id=channel_id, pts=channel_pts))
        ucc.add_channel(channel_id)

    ucc.add_user(user_id)
    users, chats, channels = await ucc.resolve()

    if (new_updates and new_updates[-1].pts >= server_pts) or not new_updates:
        return Difference(
            new_messages=new_messages,
            new_encrypted_messages=new_secret_messages,
            other_updates=other_updates,
            chats=[*chats, *channels],
            users=users,
            state=await get_state_internal(user_id),
        )
    else:
        return DifferenceSlice(
            new_messages=new_messages,
            new_encrypted_messages=new_secret_messages,
            other_updates=other_updates,
            chats=[*chats, *channels],
            users=users,
            intermediate_state=await get_state_internal(user_id, new_updates[-1].pts),
        )


@handler.on_request(GetChannelDifference, ReqHandlerFlags.DONT_FETCH_USER)
async def get_channel_difference(request: GetChannelDifference, user_id: int) -> TLChannelDifferenceBase:
    peer = await Peer.from_input_peer_raise(
        user_id, request.channel, message="CHANNEL_INVALID", code=400, peer_types=(PeerType.CHANNEL,)
    )

    server_pts = cast(
        int | None,
        await ChannelUpdate.filter(
            channel=peer.channel,
        ).annotate(max_pts=Max("pts")).first().values_list("max_pts", flat=True)
    ) or 0

    if server_pts > (request.pts + request.limit):
        dialog, _ = await Dialog.get_or_create(peer=peer, defaults={"visible": False})
        last_message = await MessageRef.filter(peer.q_this_or_channel()).select_related(
            *MessageRef.PREFETCH_MAYBECACHED,
        ).order_by("-id").first()
        if last_message:
            ucc = UsersChatsChannels()
            ucc.add_message(last_message.content_id)
            users, chats, channels = await ucc.resolve()
        else:
            users = chats = channels = []

        return ChannelDifferenceTooLong(
            final=True,
            timeout=CHANNEL_UPDATES_TIMEOUT,
            dialog=await dialog.to_tl(peer.channel.pts),
            messages=[await last_message.to_tl_maybecached(user_id)] if last_message else [],
            chats=[*chats, *channels],
            users=users,
        )

    new_updates = await ChannelUpdate.filter(
        channel=peer.channel, pts__gt=request.pts
    ).order_by("pts").limit(request.limit).select_related(*ChannelUpdate.MESSAGE_PREFETCH_MAYBECACHED)

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

    new_message_ids = {update.message_id for update in new_updates if update.type is ChannelUpdateType.NEW_MESSAGE}
    update_by_message_id = {update.message_id: update for update in new_updates if update.message_id is not None}
    all_messages = [update.message for update in new_updates if update.message_id is not None]

    other_updates = []
    ucc = UsersChatsChannels()

    for message in all_messages:
        ucc.add_message(message.content_id)

    all_messages_tl = await MessageRef.to_tl_bulk_maybecached(all_messages, user_id)
    new_messages = [
        message
        for message in all_messages_tl
        if update_by_message_id[message.id].type is ChannelUpdateType.NEW_MESSAGE
    ]
    edited_messages = {
        message.id: message
        for message in all_messages_tl
        if update_by_message_id[message.id].type is ChannelUpdateType.EDIT_MESSAGE
    }

    for update in new_updates:
        if update.type is ChannelUpdateType.EDIT_MESSAGE and update.message_id in new_message_ids:
            continue

        update_tl = await update.to_tl(ucc, edited_messages)
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
