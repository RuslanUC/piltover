from piltover.db.models import User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import Client, MessageHandler
from piltover.tl_new import InputUserSelf, PeerSettings, PeerNotifySettings, TLObject, UserEmpty
from piltover.tl_new.functions.users import GetFullUser, GetUsers
from piltover.tl_new.types import UserFull as FullUser
from piltover.tl_new.types.users import UserFull

handler = MessageHandler("users")


# noinspection PyUnusedLocal
@handler.on_request(GetFullUser, ReqHandlerFlags.AUTH_REQUIRED)
async def get_full_user(client: Client, request: GetFullUser, user: User):
    if (target_user := await User.from_input_peer(request.id, user)) is None:
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

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
        ),
        chats=[],
        users=[await target_user.to_tl(current_user=user)],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetUsers, ReqHandlerFlags.AUTH_REQUIRED)
async def get_users(client: Client, request: GetUsers, user: User):
    result: list[TLObject] = []
    for peer in request.id:
        if isinstance(peer, InputUserSelf):
            result.append(await user.to_tl(current_user=user))
        else:
            # TODO: other input users
            result.append(UserEmpty(id=0))
    return result
