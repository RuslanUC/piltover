from asyncio import sleep
from datetime import timedelta, datetime, UTC
from io import BytesIO

from loguru import logger
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.bots import process_callback_query
from piltover.app.utils.utils import check_password_internal
from piltover.context import request_ctx
from piltover.db.enums import PeerType, ChatBannedRights, InlineQueryPeer
from piltover.db.models import User, Peer, Message, UserPassword, CallbackQuery
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, InvalidConstructorException, Unreachable
from piltover.tl import KeyboardButtonCallback, ReplyInlineMarkup, InputPeerEmpty
from piltover.tl.functions.messages import GetBotCallbackAnswer, SetBotCallbackAnswer, GetInlineBotResults
from piltover.tl.types.messages import BotCallbackAnswer, BotResults
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
        ctx = request_ctx.get()
        pubsub = ctx.worker.pubsub

        query = await CallbackQuery.create(user=user, message=message_for_bot, data=request.data)

        topic = f"bot-callback-query/{query.id}"
        await pubsub.listen(topic, None)
        await upd.bot_callback_query(message_for_bot.author, query)

        result = await pubsub.listen(topic, 15)
        if result is None:
            await query.delete()
            raise ErrorRpc(error_code=400, error_message="BOT_RESPONSE_TIMEOUT")

        try:
            answer = BotCallbackAnswer.read(BytesIO(result))
        except InvalidConstructorException as e:
            logger.opt(exception=e).warning("Failed to read bot callback answer")
            raise ErrorRpc(error_code=400, error_message="BOT_RESPONSE_TIMEOUT")

        return answer


@handler.on_request(SetBotCallbackAnswer, ReqHandlerFlags.USER_NOT_ALLOWED)
async def set_bot_callback_answer(request: SetBotCallbackAnswer, user: User) -> bool:
    if request.message and len(request.message) > 240:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_TOO_LONG")

    ctx = request_ctx.get()

    async with in_transaction():
        query = await CallbackQuery.select_for_update(no_key=True).get_or_none(
            message__author=user, id=request.query_id, created_at__gte=datetime.now(UTC) - timedelta(seconds=15),
            inline=False,
        )
        if query is None:
            raise ErrorRpc(error_code=400, error_message="QUERY_ID_INVALID")

        await ctx.worker.pubsub.notify(
            topic=f"bot-callback-query/{query.id}",
            data=BotCallbackAnswer(
                alert=request.alert,
                has_url=request.url is not None,
                native_ui=True,
                message=request.message,
                url=request.url,
                cache_time=request.cache_time,
            ).write(),
        )

        await query.delete()

    return True


@handler.on_request(GetInlineBotResults, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_inline_bot_results(request: GetInlineBotResults, user: User) -> BotResults:
    bot = await Peer.from_input_peer_raise(user, request.bot)
    if bot.type is not PeerType.USER or not bot.user.bot:
        raise ErrorRpc(error_code=400, error_message="BOT_INVALID")

    if isinstance(request.peer, InputPeerEmpty):
        query_peer = None
    else:
        peer = await Peer.from_input_peer_raise(user, request.peer)
        if peer.type is PeerType.SELF:
            query_peer = InlineQueryPeer.USER
        elif peer.type is PeerType.USER and peer.user.bot and peer.user_id == bot.user_id:
            query_peer = InlineQueryPeer.SAME_BOT
        elif peer.type is PeerType.USER and peer.user.bot:
            query_peer = InlineQueryPeer.BOT
        elif peer.type is PeerType.USER:
            query_peer = InlineQueryPeer.USER
        elif peer.type is PeerType.CHAT:
            query_peer = InlineQueryPeer.CHAT
        elif peer.type is PeerType.CHANNEL and peer.channel.channel:
            query_peer = InlineQueryPeer.CHANNEL
        elif peer.type is PeerType.CHANNEL and peer.channel.supergroup:
            query_peer = InlineQueryPeer.SUPERGROUP
        else:
            query_peer = None

    if bot.user.system:
        ...  # TODO: process inline query by builtin bot
        # resp = await process_callback_query(peer, message, request.data)
        # if resp is None:
        #    raise ErrorRpc(error_code=400, error_message="BOT_RESPONSE_TIMEOUT")
        #return resp
        raise Unreachable
    else:
        ctx = request_ctx.get()
        pubsub = ctx.worker.pubsub

        query = await CallbackQuery.create(
            user=user,
            inline=True,
            data=request.query.encode("utf8"),
            offset=request.offset[:64],
            inline_peer=query_peer,
        )

        topic = f"bot-inline-query/{query.id}"
        await pubsub.listen(topic, None)
        await upd.bot_inline_query(bot.user, query)

        result = await pubsub.listen(topic, 15)
        if result is None:
            await query.delete()
            raise ErrorRpc(error_code=400, error_message="BOT_RESPONSE_TIMEOUT")

        try:
            results = BotResults.read(BytesIO(result))
        except InvalidConstructorException as e:
            logger.opt(exception=e).warning("Failed to read bot inline answer")
            raise ErrorRpc(error_code=400, error_message="BOT_RESPONSE_TIMEOUT")

        return results


# TODO: SetInlineBotResults
