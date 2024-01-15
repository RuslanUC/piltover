from loguru import logger

from piltover.db.models import User
from piltover.exceptions import ErrorRpc
from piltover.high_level import Client, MessageHandler
from piltover.tl_new import InputUserSelf, PeerSettings, PeerNotifySettings, TLObject, UserEmpty, InputUser
from piltover.tl_new.functions.users import GetFullUser, GetUsers
from piltover.tl_new.types import UserFull as FullUser
from piltover.tl_new.types.users import UserFull

handler = MessageHandler("users")


# noinspection PyUnusedLocal
@handler.on_request(GetFullUser, True)
async def get_full_user(client: Client, request: GetFullUser, user: User):
    if isinstance(request.id, InputUser) and request.id.user_id == user.id:
        request.id = InputUserSelf()

    if isinstance(request.id, InputUserSelf):
        return UserFull(
            full_user=FullUser(
                can_pin_message=True,
                voice_messages_forbidden=True,
                id=user.id,
                about=user.about,
                settings=PeerSettings(),
                profile_photo=await user.get_photo(user),
                notify_settings=PeerNotifySettings(show_previews=True),
                common_chats_count=0,
            ),
            chats=[],
            users=[await user.to_tl(current_user=user)],
        )

    logger.warning("id: inputUser is not inputUserSelf: not implemented")
    raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")


# noinspection PyUnusedLocal
@handler.on_request(GetUsers, True)
async def get_users(client: Client, request: GetUsers, user: User):
    result: list[TLObject] = []
    for peer in request.id:
        if isinstance(peer, InputUserSelf):
            result.append(await user.to_tl(current_user=user))
        else:
            # TODO: other input users
            result.append(UserEmpty(id=0))
    return result
