from typing import cast

from tortoise import Tortoise
from tortoise.expressions import Q, Subquery
from tortoise.functions import Max

from piltover.context import request_ctx
from piltover.db.enums import PeerType, PrivacyRuleKeyType
from piltover.db.models import User, Peer, PrivacyRule, Contact, Channel, ChatParticipant, MessageRef, Wallpaper, \
    Username, UserBackgroundEmojis, UserEmojiStatus, BotInfo, File
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
    peer_type, peer_user_id = Peer.type_and_id_from_input_raise(user_id, request.id)
    if peer_type not in (PeerType.SELF, PeerType.USER):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    conn = Tortoise.get_connection("default")

    rows, results = await conn.execute_query(
        """
        SELECT 
            peer.id peer_id, peer.user_has_wallpaper, peer.user_ttl_period_days, peer.blocked_at,
            
            user.id user__id, user.phone_number, user.first_name, user.last_name, user.lang_code, user.about, user.birthday,
            user.bot, user.deleted, user.read_dates_private, user.version user__version, user.accent_color_id, user.profile_color_id,
            
            username.username,
            
            userbackgroundemojis.id backgroundemojis__id, userbackgroundemojis.accent_emoji_id, 
            userbackgroundemojis.profile_emoji_id,
            
            useremojistatus.emoji_id, useremojistatus.until,
            
            botinfo.id botinfo__id, botinfo.description, botinfo.description_photo_id, botinfo.privacy_policy_url, 
            botinfo.version botinfo__version,
            
            botinfo_description_photo.id botinfo_description_photo_id, botinfo_description_photo.created_at, botinfo_description_photo.photo_sizes, 
            botinfo_description_photo.photo_stripped, botinfo_description_photo.photo_path,
            botinfo_description_photo.constant_access_hash, botinfo_description_photo.constant_file_ref
        FROM user
            INNER JOIN peer on peer.owner_id = %s and user.id = peer.user_id
            LEFT OUTER JOIN username on username.user_id = user.id
            LEFT OUTER JOIN userbackgroundemojis on userbackgroundemojis.user_id = user.id
            LEFT OUTER JOIN useremojistatus on useremojistatus.user_id = user.id
            LEFT OUTER JOIN botinfo on botinfo.user_id = user.id
            LEFT OUTER JOIN file botinfo_description_photo on botinfo_description_photo.id = botinfo.description_photo_id
        WHERE user.id = %s
        """,
        [user_id, peer_user_id]
    )

    row = results[0]

    if row["username"] is not None:
        _username = Username(username=row["username"])
        _username._saved_in_db = True
    else:
        _username = None

    if row["backgroundemojis__id"] is not None:
        _emojis = UserBackgroundEmojis(accent_emoji_id=row["accent_emoji_id"], profile_emoji_id=row["profile_emoji_id"])
        _emojis._saved_in_db = True
    else:
        _emojis = None

    if row["emoji_id"] is not None:
        _emojistatus = UserEmojiStatus(emoji_id=row["emoji_id"], until=row["until"])
        _emojistatus._saved_in_db = True
    else:
        _emojistatus = None

    if row["botinfo__id"] is not None:
        _botinfo = BotInfo(
            id=row["botinfo__id"],
            description=row["description"],
            description_photo_id=row["description_photo_id"],
            privacy_policy_url=row["privacy_policy_url"],
            version=row["botinfo__version"],
        )
        _botinfo._saved_in_db = True

        if row["botinfo_description_photo_id"] is not None:
            _botinfo_description_photo = File(
                id=row["botinfo_description_photo_id"],
                created_at=row["created_at"],
                photo_sizes=row["photo_sizes"],
                photo_stripped=row["photo_stripped"],
                photo_path=row["photo_path"],
                constant_access_hash=row["constant_access_hash"],
                constant_file_ref=row["constant_file_ref"],
            )
            _botinfo_description_photo._saved_in_db = True
            _botinfo.description_photo = _botinfo_description_photo
    else:
        _botinfo = None

    _user = User(
        id=row["user__id"],
        phone_number=row["phone_number"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        lang_code=row["lang_code"],
        about=row["about"],
        birthday=row["birthday"],
        bot=row["bot"],
        deleted=row["deleted"],
        read_dates_private=row["read_dates_private"],
        version=row["user__version"],
        accent_color_id=row["accent_color_id"],
        profile_color_id=row["profile_color_id"],
    )
    _user._username = _username
    _user._background_emojis = _emojis
    _user._emoji_status = _emojistatus
    _user._bot_info = _botinfo
    _user._saved_in_db = True

    peer = Peer(
        id=row["peer_id"],
        type=peer_type,
        owner_id=user_id,
        user_id=peer_user_id,
        user_has_wallpaper=row["user_has_wallpaper"],
        user_ttl_period_days=row["user_ttl_period_days"],
        blocked_at=row["blocked_at"],
        user=_user,
    )

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

    has_scheduled = await MessageRef.filter(peer=peer, scheduled_by_user_id=user_id).exists()
    pinned_msg_id = cast(
        int | None,
        cast(
            object,
            await MessageRef.filter(
                peer=peer, pinned=True,
            ).annotate(max_id=Max("id")).first().values_list("max_id", flat=True)
        )
    )

    personal_channel = await Channel.get_or_none(
        userpersonalchannels__user=target_user,
    ).select_related("peer").only("id", "version", "peer__id")
    if personal_channel is not None:
        personal_channel_msg_id = cast(
            int | None,
            cast(
                object,
                await MessageRef.filter(
                    peer_id=personal_channel.peer.id,
                ).annotate(max_id=Max("id")).first().values_list("max_id", flat=True)
            )
        ) or 0
    else:
        personal_channel_msg_id = None

    bot_info = None
    if target_user.bot is not None:
        if target_user.bot_info is None:
            bot_info = TLBotInfo()
        else:
            bot_info = await target_user.bot_info.to_tl()

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
    auth_id = cast(int, request_ctx.get().auth_id)

    user_ids = set()
    contact_ids = set()

    for peer in request.id:
        if isinstance(peer, _InputUsers) and peer.access_hash == 0:
            contact_ids.add(peer.user_id)
            continue

        if Peer.input_is_self(user_id, peer) and user_id not in user_ids:
            user_ids.add(user_id)
            continue

        if isinstance(peer, _InputUsers):
            if not User.check_access_hash(user_id, auth_id, peer.user_id, peer.access_hash):
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
