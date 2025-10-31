from typing import cast

from piltover.db.enums import PeerType, PrivacyRuleKeyType
from piltover.db.models import User, Peer, PrivacyRule, ChatWallpaper, Contact, Message, Channel
from piltover.exceptions import ErrorRpc
from piltover.tl import PeerSettings, PeerNotifySettings, TLObjectVector
from piltover.tl.functions.users import GetFullUser, GetUsers
from piltover.tl.types import UserFull as FullUser, InputUser
from piltover.tl.types.users import UserFull
from piltover.worker import MessageHandler

handler = MessageHandler("users")


@handler.on_request(GetFullUser)
async def get_full_user(request: GetFullUser, user: User):
    peer = await Peer.from_input_peer_raise(user, request.id)
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
            read_dates_private=True,
            wallpaper=await chat_wallpaper.wallpaper.to_tl(user) if chat_wallpaper is not None else None,
            has_scheduled=has_scheduled,
            ttl_period=bool(peer.user_ttl_period_days),
            pinned_msg_id=pinned_msg_id,
            personal_channel_id=personal_channel.make_id() if personal_channel is not None else None,
            personal_channel_message=personal_channel_msg_id,
        ),
        chats=[await personal_channel.to_tl(user)] if personal_channel is not None else [],
        users=[await target_user.to_tl(user)],
    )


@handler.on_request(GetUsers)
async def get_users(request: GetUsers, user: User):
    result = TLObjectVector()
    for peer in request.id:
        if isinstance(peer, InputUser) and peer.access_hash == 0:
            contact = await Contact.get_or_none(owner=user, target__id=peer.user_id).select_related("target")
            if contact is not None:
                result.append(await contact.target.to_tl(user))
            continue

        try:
            out_peer = await Peer.from_input_peer(user, peer)
            if not out_peer:
                continue
            target_user = user if out_peer.type is PeerType.SELF else out_peer.user
            result.append(await target_user.to_tl(user))
        except ErrorRpc:
            ...

    return result
