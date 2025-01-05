from piltover.db.enums import PeerType
from piltover.db.models import User, Peer
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.tl import PeerSettings, TLObject, UserEmpty, PeerNotifySettings
from piltover.tl.functions.users import GetFullUser, GetUsers
from piltover.tl.types import UserFull as FullUser
from piltover.tl.types.users import UserFull

handler = MessageHandler("users")


@handler.on_request(GetFullUser)
async def get_full_user(request: GetFullUser, user: User):
    if (peer := await Peer.from_input_peer(user, request.id)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    target_user = peer.peer_user(user)

    return UserFull(
        full_user=FullUser(
            can_pin_message=True,
            voice_messages_forbidden=True,
            id=target_user.id,
            about=target_user.about,
            settings=PeerSettings(),
            profile_photo=await target_user.get_photo(user),
            notify_settings=PeerNotifySettings(show_previews=True),
            common_chats_count=0,
            birthday=target_user.to_tl_birthday()
        ),
        chats=[],
        users=[await target_user.to_tl(current_user=user)],
    )


@handler.on_request(GetUsers)
async def get_users(request: GetUsers, user: User):
    result: list[TLObject] = []
    for peer in request.id:
        try:
            out_peer = await Peer.from_input_peer(user, peer)
            if out_peer:
                target_user = user if out_peer.type is PeerType.SELF else out_peer.user
                result.append(await target_user.to_tl(user))
            else:
                result.append(UserEmpty(id=0))
        except ErrorRpc:
            result.append(UserEmpty(id=0))

    return result
