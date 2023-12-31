from loguru import logger

from piltover.app.utils import auth_required
from piltover.db.models import User
from piltover.exceptions import ErrorRpc
from piltover.server import Client, MessageHandler
from piltover.tl.types import CoreMessage
from piltover.tl_new import InputUserSelf, PeerSettings, PeerNotifySettings, TLObject, UserEmpty
from piltover.tl_new.functions.users import GetFullUser, GetUsers
from piltover.tl_new.types import UserFull as FullUser
from piltover.tl_new.types.users import UserFull

handler = MessageHandler("users")


# noinspection PyUnusedLocal
@handler.on_message(GetFullUser)
@auth_required
async def get_full_user(client: Client, request: CoreMessage[GetFullUser], session_id: int, user: User):
    if isinstance(request.obj.id, InputUserSelf):
        return UserFull(
            full_user=FullUser(
                can_pin_message=True,
                voice_messages_forbidden=True,
                id=user.id,
                #about=user.about,
                about="",
                settings=PeerSettings(),
                profile_photo=None,
                notify_settings=PeerNotifySettings(show_previews=True),
                common_chats_count=0,
            ),
            chats=[],
            users=[user.to_tl(is_self=True)],
        )

    logger.warning("id: inputUser is not inputUserSelf: not implemented")
    raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")


# noinspection PyUnusedLocal
@handler.on_message(GetUsers)
@auth_required
async def get_users(client: Client, request: CoreMessage[GetUsers], session_id: int, user: User):
    result: list[TLObject] = []
    for peer in request.obj.id:
        if isinstance(peer, InputUserSelf):
            result.append(user.to_tl(is_self=True))
        else:
            # TODO: other input users
            result.append(UserEmpty(id=0))
    return result
