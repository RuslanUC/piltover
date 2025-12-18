from asyncio import sleep
from datetime import timedelta, datetime, UTC
from io import BytesIO

from loguru import logger
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.bots import process_callback_query
from piltover.app.utils.utils import check_password_internal, process_message_entities
from piltover.context import request_ctx
from piltover.db.enums import PeerType, ChatBannedRights, InlineQueryPeer, FileType, InlineQueryResultType
from piltover.db.models import User, Peer, Message, UserPassword, CallbackQuery, InlineQuery, File
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, InvalidConstructorException, Unreachable
from piltover.tl import KeyboardButtonCallback, ReplyInlineMarkup, InputPeerEmpty, InputBotInlineResult, \
    InputBotInlineMessageText, BotInlineResult, BotInlineMessageText, objects, InputBotInlineMessageMediaAuto, \
    BotInlineMessageMediaAuto, InputBotInlineResultPhoto, InputBotInlineResultDocument, BotInlineMediaResult, \
    InputPhoto, InputDocument
from piltover.tl.functions.messages import GetBotCallbackAnswer, SetBotCallbackAnswer, GetInlineBotResults, \
    SetInlineBotResults
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

    cached = await InlineQuery.filter(
        Q(user=user, private=True) | Q(private=False),
        query=request.query,
        offset=request.offset[:64],
        bot=bot,
        inline_peer=query_peer,
        cached_until__gte=datetime.now(UTC),
        cached_data__not_isnull=True,
    ).order_by("-id").first()

    if cached is not None:
        try:
            cached_result = BotResults.read(BytesIO(cached.cached_data))
        except InvalidConstructorException as e:
            logger.opt(exception=e).warning("Failed to read cached bot inline answer")
        else:
            return cached_result

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

        query = await InlineQuery.create(
            user=user,
            bot=bot.user,
            data=request.query[:128],
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


async def _process_entities_tl(text: str, entities: list[...], user: User) -> list[...] | None:
    entities_dict = await process_message_entities(text, entities, user)
    result = []
    for entity in entities_dict:
        tl_id = entity.pop("_")
        result.append(objects[tl_id](**entity))

    return result or None


_DOCUMENT_RESULT_TYPES = {
    InlineQueryResultType.STICKER, InlineQueryResultType.GIF, InlineQueryResultType.VOICE,
    InlineQueryResultType.VIDEO, InlineQueryResultType.AUDIO, InlineQueryResultType.FILE
}


@handler.on_request(SetInlineBotResults, ReqHandlerFlags.USER_NOT_ALLOWED)
async def set_inline_bot_results(request: SetInlineBotResults, user: User) -> bool:
    ctx = request_ctx.get()
    cache_time = 300 if request.cache_time <= 0 else request.cache_time
    cache_until = datetime.now(UTC) + timedelta(seconds=cache_time)

    async with in_transaction():
        query = await InlineQuery.select_for_update(no_key=True).get_or_none(
            id=request.query_id, bot=user, created_at__gte=datetime.now(UTC) - timedelta(seconds=15),
        )
        if query is None:
            raise ErrorRpc(error_code=400, error_message="QUERY_ID_INVALID")

        results = []
        for result in request.results:
            if not isinstance(result, (InputBotInlineResult, InputBotInlineResultPhoto, InputBotInlineResultDocument)):
                raise ErrorRpc(error_code=400, error_message="RESULT_TYPE_INVALID")

            type_ = result.type_.lower()
            if type_ not in InlineQueryResultType._value2member_map_:
                raise ErrorRpc(error_code=400, error_message="RESULT_TYPE_INVALID")

            result_type = InlineQueryResultType(type_)

            message = result.send_message
            if isinstance(message, InputBotInlineMessageText):
                send_message = BotInlineMessageText(
                    no_webpage=message.no_webpage,
                    invert_media=message.invert_media,
                    message=message.message,
                    entities=await _process_entities_tl(message.message, message.entities, user),
                    reply_markup=None,  # TODO: support reply markup in inline results
                )
            elif isinstance(message, InputBotInlineMessageMediaAuto):
                send_message = BotInlineMessageMediaAuto(
                    invert_media=message.invert_media,
                    message=message.message,
                    entities=await _process_entities_tl(message.message, message.entities, user),
                    reply_markup=None,  # TODO: support reply markup in inline results
                )
            else:
                # TODO: add other message types and replace with `Unreachable`
                raise ErrorRpc(error_code=400, error_message="RESULT_TYPE_INVALID")

            if isinstance(result, InputBotInlineResult):
                if result.content is not None:
                    # TODO: download content in worker or something
                    raise ErrorRpc(error_code=501, error_message="NOT_IMPLEMENTED")

                results.append(BotInlineResult(
                    id=result.id,
                    type_=type_,
                    title=result.title,
                    description=result.description,
                    url=result.url,
                    send_message=send_message,
                ))
            elif isinstance(result, InputBotInlineResultPhoto):
                if result_type is not InlineQueryResultType.PHOTO:
                    raise ErrorRpc(error_code=400, error_message="RESULT_TYPE_INVALID")

                if not isinstance(result.photo, InputPhoto):
                    raise ErrorRpc(error_code=400, error_message="PHOTO_INVALID")

                photo = await File.from_input(
                    user.id, result.photo.id, result.photo.access_hash, result.photo.file_reference, FileType.PHOTO,
                )
                if photo is None:
                    raise ErrorRpc(error_code=400, error_message="PHOTO_INVALID")

                results.append(BotInlineMediaResult(
                    id=result.id,
                    type_=type_,
                    photo=photo.to_tl_photo(),
                    send_message=send_message,
                ))
            elif isinstance(result, InputBotInlineResultDocument):
                if result_type not in _DOCUMENT_RESULT_TYPES:
                    raise ErrorRpc(error_code=400, error_message="RESULT_TYPE_INVALID")

                if not isinstance(result.document, InputDocument):
                    raise ErrorRpc(error_code=400, error_message="DOCUMENT_INVALID")

                input_doc = result.document
                doc = await File.from_input(
                    user.id, input_doc.id, input_doc.access_hash, input_doc.file_reference, FileType.PHOTO,
                )
                if doc is None:
                    raise ErrorRpc(error_code=400, error_message="DOCUMENT_INVALID")

                results.append(BotInlineMediaResult(
                    id=result.id,
                    type_=type_,
                    document=doc.to_tl_document(),
                    title=result.title,
                    description=result.description,
                    send_message=send_message,
                ))

        bot_result = BotResults(
            query_id=request.query_id,
            results=results,
            cache_time=cache_time,
            users=[],
            gallery=request.gallery,
            next_offset=request.next_offset[:64] if request.next_offset is not None else None,
            switch_pm=None,  # TODO: implement switch_pm
            switch_webview=None,
        ).write()

        query.cached_data = bot_result
        query.cache_until = cache_until
        query.cache_private = request.private
        await query.save(update_fields=["cached_data", "cache_until", "cache_private"])

        await ctx.worker.pubsub.notify(
            topic=f"bot-inline-query/{query.id}",
            data=bot_result,
        )

    return True

# TODO: SendInlineBotResult
