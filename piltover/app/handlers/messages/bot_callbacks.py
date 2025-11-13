from asyncio import sleep
from datetime import timedelta, datetime, UTC

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.bots import process_callback_query
from piltover.app.utils.utils import check_password_internal
from piltover.db.enums import PeerType, ChatBannedRights
from piltover.db.models import User, Peer, Message, UserPassword, CallbackQuery
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import KeyboardButtonCallback, ReplyInlineMarkup
from piltover.tl.functions.messages import GetBotCallbackAnswer, SetBotCallbackAnswer
from piltover.tl.types.messages import BotCallbackAnswer
from piltover.worker import MessageHandler

handler = MessageHandler("messages.bot_callbacks")


@handler.on_request(GetBotCallbackAnswer, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_bot_callback_answer(request: GetBotCallbackAnswer, user: User) -> BotCallbackAnswer:
    if not request.data:  # in what case would data be None ??????
        raise ErrorRpc(error_code=400, error_message="DATA_INVALID")

    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        # TODO: allow no participant in public channels
        participant = await chat_or_channel.get_participant_raise(user)
        # TODO: check if this is correct permission
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.VIEW_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")
        channel_min_id = 0
        if peer.type is PeerType.CHANNEL \
                and (channel_min_id := peer.channel.min_id(participant)) is not None \
                and request.msg_id < channel_min_id:
            raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if (message := await Message.get_(request.msg_id, peer)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if not message.author.bot:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    builtin_bot = message.author.system

    kbd = message.make_reply_markup()
    if kbd is None or not isinstance(kbd, ReplyInlineMarkup):
        raise ErrorRpc(error_code=400, error_message="DATA_INVALID")

    message_for_bot = None
    if not builtin_bot and (message_for_bot := await message.get_for_user(message.author)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    button: KeyboardButtonCallback | None = None
    for row in kbd.rows:
        await sleep(0)
        for btn in row.buttons:
            if isinstance(btn, KeyboardButtonCallback) and btn.data == request.data:
                button = btn
                break
        if button is not None:
            break
    else:
        raise ErrorRpc(error_code=400, error_message="DATA_INVALID")

    if button.requires_password:
        password = await UserPassword.get_or_none(user=user)
        if password is None or password.password is None:
            raise ErrorRpc(error_code=400, error_message="PASSWORD_MISSING")
        await check_password_internal(password, request.password)

    if builtin_bot:
        if peer.type is not PeerType.USER:
            raise ErrorRpc(error_code=400, error_message="DATA_INVALID")
        resp = await process_callback_query(peer, message, request.data)
        if resp is None:
            raise ErrorRpc(error_code=400, error_message="BOT_RESPONSE_TIMEOUT")
        return resp
    else:
        query = await CallbackQuery.create(user=user, message=message_for_bot, data=request.data)
        await upd.bot_callback_query(message_for_bot.author, query)

        for _ in range(15):
            await sleep(1)
            await query.refresh_from_db(fields=[
                "response",
                "response_alert",
                "response_message",
                "response_url",
                "cache_time",
            ])
            if query.response:
                break
        else:
            await query.delete()
            raise ErrorRpc(error_code=400, error_message="BOT_RESPONSE_TIMEOUT")

        return BotCallbackAnswer(
            alert=query.response_alert,
            has_url=query.response_url is not None,
            native_ui=True,
            message=query.response_message,
            url=query.response_url,
            cache_time=query.cache_time,
        )


@handler.on_request(SetBotCallbackAnswer, ReqHandlerFlags.USER_NOT_ALLOWED)
async def set_bot_callback_answer(request: SetBotCallbackAnswer, user: User) -> bool:
    if request.message and len(request.message) > 240:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_TOO_LONG")

    query = await CallbackQuery.get_or_none(
        message__author=user, id=request.query_id, created_at__gte=datetime.now(UTC) - timedelta(seconds=15),
    )

    if query is None:
        raise ErrorRpc(error_code=400, error_message="QUERY_ID_INVALID")
    if query.response:
        return True

    query.response = True
    query.response_message = request.message
    query.response_url = request.url
    query.response_alert = request.alert
    query.cache_time = request.cache_time
    await query.save(update_fields=[
        "response",
        "response_message",
        "response_url",
        "response_alert",
        "cache_time",
    ])

    return True
