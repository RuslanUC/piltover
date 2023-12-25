from loguru import logger

from piltover.app import user
from piltover.server import Client, MessageHandler
from piltover.tl.types import CoreMessage
from piltover.tl_new import InputUserSelf, PeerSettings, PeerNotifySettings, TLObject, UserEmpty
from piltover.tl_new.functions.users import GetFullUser, GetUsers
from piltover.tl_new.types import UserFull as FullUser
from piltover.tl_new.types.users import UserFull

handler = MessageHandler("auth")


# noinspection PyUnusedLocal
@handler.on_message(GetFullUser)
async def get_full_user(client: Client, request: CoreMessage, session_id: int):
    if isinstance(request.obj, InputUserSelf):
        return UserFull(
            full_user=FullUser(
                flags=0,
                blocked=False,
                phone_calls_available=False,
                phone_calls_private=False,
                can_pin_message=True,
                has_scheduled=False,
                video_calls_available=False,
                voice_messages_forbidden=True,
                id=user.id,
                about="hi, this is a test bio",
                settings=PeerSettings(),
                profile_photo=None,
                notify_settings=PeerNotifySettings(
                    show_previews=True,
                    silent=False,
                ),
                common_chats_count=0,
            ),
            chats=[],
            users=[user],
        )
    logger.warning("id: inputUser is not inputUserSelf: not implemented")


# noinspection PyUnusedLocal
@handler.on_message(GetUsers)
async def get_users(client: Client, request: CoreMessage[GetUsers], session_id: int):
    result: list[TLObject] = []
    for peer in request.obj.id:
        if isinstance(peer, InputUserSelf):
            result.append(user)
        else:
            # TODO: other input users
            result.append(UserEmpty(id=0))
    return result
