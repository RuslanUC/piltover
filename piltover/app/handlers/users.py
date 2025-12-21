from typing import cast

from tortoise.expressions import Q, Subquery

from piltover.context import request_ctx
from piltover.db.enums import PeerType, PrivacyRuleKeyType
from piltover.db.models import User, Peer, PrivacyRule, ChatWallpaper, Contact, Message, Channel, BotInfo
from piltover.tl import PeerSettings, PeerNotifySettings, TLObjectVector
from piltover.tl.functions.users import GetFullUser, GetUsers
from piltover.tl.types import UserFull as FullUser, InputUser, BotInfo as TLBotInfo, InputUserSelf, \
    InputUserFromMessage, InputPeerUser, InputPeerSelf, InputPeerUserFromMessage
from piltover.tl.types.users import UserFull
from piltover.worker import MessageHandler

handler = MessageHandler("users")


@handler.on_request(GetFullUser)
async def get_full_user(request: GetFullUser, user: User):
    peer = await Peer.from_input_peer_raise(user, request.id, peer_types=(PeerType.SELF, PeerType.USER))
    target_user = peer.peer_user(user)

    about = ""
    if await PrivacyRule.has_access_to(user, target_user, PrivacyRuleKeyType.ABOUT):
        about = target_user.about

    chat_wallpaper = await ChatWallpaper.get_or_none(user=user, target=target_user).select_related(
        "wallpaper", "wallpaper__document", "wallpaper__settings",
    )

    has_scheduled = await Message.filter(peer=peer, scheduled_date__not_isnull=True).exists()
    pinned_msg_id = cast(
        int | None,
        await Message.filter(peer=peer, pinned=True).order_by("-id").first().values_list("id", flat=True),
    )

    personal_channel = await Channel.get_or_none(userpersonalchannels__user=target_user)
    if personal_channel is not None:
        personal_channel_msg_id = cast(
            int | None,
            await Message.filter(
                peer__owner=None, peer__channel=personal_channel,
            ).order_by("-id").first().values_list("id", flat=True),
        )
    else:
        personal_channel_msg_id = None

    if personal_channel is not None:
        await Peer.get_or_create(owner=user, type=PeerType.CHANNEL, channel=personal_channel)

    bot_info = None
    if target_user.bot:
        bot_info = await BotInfo.get_or_none(user=target_user)
        if bot_info is None:
            bot_info = TLBotInfo()
        else:
            bot_info = bot_info.to_tl()

    return UserFull(
        full_user=FullUser(
            can_pin_message=True,
            id=target_user.id,
            about=about,
            settings=PeerSettings(),
            profile_photo=await target_user.get_photo(user),
            notify_settings=PeerNotifySettings(show_previews=True),
            common_chats_count=0,
            birthday=await target_user.to_tl_birthday(user),
            read_dates_private=user.read_dates_private,
            wallpaper=chat_wallpaper.wallpaper.to_tl() if chat_wallpaper is not None else None,
            has_scheduled=has_scheduled,
            ttl_period=peer.user_ttl_period_days * 86400 if peer.user_ttl_period_days else None,
            pinned_msg_id=pinned_msg_id,
            personal_channel_id=personal_channel.make_id() if personal_channel is not None else None,
            personal_channel_message=personal_channel_msg_id,
            bot_info=bot_info,
            blocked=peer.blocked_at is not None,
            phone_calls_available=True,
            phone_calls_private=False,
            # video_calls_available=True,
        ),
        chats=[await personal_channel.to_tl(user)] if personal_channel is not None else [],
        users=[await target_user.to_tl(user, peer)],
    )


_InputUsers = (InputUser, InputPeerUser)
_InputUsersSelf = (InputUserSelf, InputPeerSelf)
_InputUsersInclMessage = (*_InputUsers, InputUserFromMessage, InputPeerUserFromMessage)


@handler.on_request(GetUsers)
async def get_users(request: GetUsers, user: User):
    ctx = request_ctx.get()

    user_ids = set()
    contact_ids = set()

    for peer in request.id:
        if isinstance(peer, _InputUsers) and peer.access_hash == 0:
            contact_ids.add(peer.user_id)
            continue

        is_self = isinstance(peer, _InputUsersSelf) \
                  or (isinstance(peer, _InputUsersInclMessage) and peer.user_id == user.id)
        if is_self and user.id not in user_ids:
            await Peer.get_or_create(owner=user, user=user, type=PeerType.SELF)
            user_ids.add(user.id)
            continue

        if isinstance(peer, _InputUsers):
            if not User.check_access_hash(user.id, ctx.auth_id, peer.user_id, peer.access_hash):
                continue
            user_ids.add(peer.user_id)

        # TODO: *FromMessage

    users = await User.filter(
        Q(id__in=user_ids)
        | Q(id__in=Subquery(
            Contact.filter(owner=user, target__id__in=contact_ids).values_list("target_id", flat=True)
        ))
    )

    if users:
        return TLObjectVector(await User.to_tl_bulk(users, user))
    else:
        return TLObjectVector()
