from typing import cast

from tortoise.expressions import Q, Subquery

from piltover.context import request_ctx
from piltover.db.enums import PeerType, PrivacyRuleKeyType
from piltover.db.models import User, Peer, PrivacyRule, Contact, Channel, BotInfo, ChatParticipant, MessageRef, \
    Wallpaper
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import PeerSettings, PeerNotifySettings, TLObjectVector
from piltover.tl.functions.users import GetFullUser, GetUsers
from piltover.tl.types import UserFull as FullUser, InputUser, BotInfo as TLBotInfo, InputUserSelf, \
    InputUserFromMessage, InputPeerUser, InputPeerSelf, InputPeerUserFromMessage
from piltover.tl.types.users import UserFull
from piltover.worker import MessageHandler

handler = MessageHandler("users")


@handler.on_request(GetFullUser, ReqHandlerFlags.DONT_FETCH_USER)
async def get_full_user(request: GetFullUser, user_id: int) -> UserFull:
    ctx = request_ctx.get()

    peer_query = Peer.query_from_input_user_or_raise(user_id, request.id, ctx.auth_id)
    peer = await peer_query.select_related("user__username", "user__background_emojis", "user__emoji_status")
    if peer is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    target_user = peer.user

    privacy_rules = await PrivacyRule.has_access_to_bulk([target_user], user_id, [
        PrivacyRuleKeyType.ABOUT,
        PrivacyRuleKeyType.BIRTHDAY,
        PrivacyRuleKeyType.PROFILE_PHOTO,
    ])
    privacy_rules = privacy_rules[target_user.id]

    if peer.user_has_wallpaper:
        wallpaper = await Wallpaper.get_or_none(
            chatwallpapers__user_id=user_id, chatwallpapers__target_id=target_user.id
        ).select_related("document", "settings")
    else:
        wallpaper = None

    has_scheduled = await MessageRef.filter(peer=peer, content__scheduled_date__not_isnull=True).exists()
    pinned_msg_id = cast(
        int | None,
        await MessageRef.filter(peer=peer, pinned=True).order_by("-id").first().values_list("id", flat=True),
    )

    personal_channel = await Channel.get_or_none(userpersonalchannels__user=target_user).only("id", "version")
    if personal_channel is not None:
        personal_channel_msg_id = cast(
            int | None,
            await MessageRef.filter(
                peer__owner=None, peer__channel=personal_channel,
            ).order_by("-id").first().values_list("id", flat=True),
        ) or 0
    else:
        personal_channel_msg_id = None

    if personal_channel is not None:
        await Peer.bulk_create(
            [Peer(owner_id=user_id, type=PeerType.CHANNEL, channel_id=personal_channel.id)],
            ignore_conflicts=True,
        )

    bot_info = None
    if target_user.bot:
        bot_info = await BotInfo.get_or_none(user=target_user)
        if bot_info is None:
            bot_info = TLBotInfo()
        else:
            bot_info = await bot_info.to_tl()

    birthday = None
    if privacy_rules[PrivacyRuleKeyType.BIRTHDAY]:
        birthday = target_user.to_tl_birthday_noprivacycheck()

    photo = None
    photo_db, photo_fallback_db = await target_user.get_db_photos()
    if privacy_rules[PrivacyRuleKeyType.PROFILE_PHOTO] and photo_db is not None:
        photo = photo_db.to_tl()
    else:
        photo_db = None

    if peer.type is PeerType.SELF:
        common_chats_count = 0
    else:
        common_chats_count = await ChatParticipant.common_chats_query(user_id, peer.user_id).count()

    return UserFull(
        full_user=FullUser(
            can_pin_message=True,
            id=target_user.id,
            about=target_user.about if privacy_rules[PrivacyRuleKeyType.ABOUT] else "",
            settings=PeerSettings(),
            profile_photo=photo,
            notify_settings=PeerNotifySettings(show_previews=True),
            common_chats_count=common_chats_count,
            birthday=birthday,
            read_dates_private=target_user.read_dates_private,
            wallpaper=wallpaper.to_tl() if wallpaper is not None else None,
            has_scheduled=has_scheduled,
            ttl_period=peer.user_ttl_period_days * 86400 if peer.user_ttl_period_days else None,
            pinned_msg_id=pinned_msg_id,
            personal_channel_id=personal_channel.make_id() if personal_channel is not None else None,
            personal_channel_message=personal_channel_msg_id,
            bot_info=bot_info,
            blocked=peer.blocked_at is not None,
            phone_calls_available=True,
            phone_calls_private=False,
            fallback_photo=photo_fallback_db.to_tl() if photo_fallback_db is not None else None,
            translations_disabled=True,
            # video_calls_available=True,
        ),
        chats=[await personal_channel.to_tl_maybecached()] if personal_channel is not None else [],
        users=[await target_user.to_tl(userphoto=photo_db)],
    )


_InputUsers = (InputUser, InputPeerUser)
_InputUsersSelf = (InputUserSelf, InputPeerSelf)
_InputUsersInclMessage = (*_InputUsers, InputUserFromMessage, InputPeerUserFromMessage)


@handler.on_request(GetUsers, ReqHandlerFlags.DONT_FETCH_USER)
async def get_users(request: GetUsers, user_id: int):
    ctx = request_ctx.get()

    user_ids = set()
    contact_ids = set()

    for peer in request.id:
        if isinstance(peer, _InputUsers) and peer.access_hash == 0:
            contact_ids.add(peer.user_id)
            continue

        is_self = isinstance(peer, _InputUsersSelf) \
                  or (isinstance(peer, _InputUsersInclMessage) and peer.user_id == user_id)
        if is_self and user_id not in user_ids:
            user_ids.add(user_id)
            continue

        if isinstance(peer, _InputUsers):
            if not User.check_access_hash(user_id, ctx.auth_id, peer.user_id, peer.access_hash):
                continue
            user_ids.add(peer.user_id)

        # TODO: *FromMessage

    users = await User.filter(
        Q(id__in=user_ids)
        | Q(id__in=Subquery(
            Contact.filter(owner_id=user_id, target_id__in=contact_ids).values_list("target_id", flat=True)
        ))
    )

    if users:
        return TLObjectVector(await User.to_tl_bulk(users))
    else:
        return TLObjectVector()
