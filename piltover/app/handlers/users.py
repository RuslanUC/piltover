from piltover.db.enums import PeerType, PrivacyRuleKeyType
from piltover.db.models import User, Peer, PrivacyRule, ChatWallpaper, Contact
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

    return UserFull(
        full_user=FullUser(
            can_pin_message=True,
            voice_messages_forbidden=True,
            id=target_user.id,
            about=about,
            settings=PeerSettings(),
            profile_photo=await target_user.get_photo(user),
            notify_settings=PeerNotifySettings(show_previews=True),
            common_chats_count=0,
            birthday=await target_user.to_tl_birthday(user),
            read_dates_private=True,
            wallpaper=await chat_wallpaper.wallpaper.to_tl(user) if chat_wallpaper is not None else None,
        ),
        chats=[],
        users=[await target_user.to_tl(current_user=user)],
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
