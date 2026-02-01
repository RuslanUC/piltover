from asyncio import sleep
from datetime import timedelta, datetime, UTC
from io import BytesIO

from loguru import logger
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.bots import process_callback_query, process_inline_query
from piltover.app.utils.utils import check_password_internal, process_message_entities
from piltover.context import request_ctx
from piltover.db.enums import PeerType, ChatBannedRights, InlineQueryPeer, FileType, InlineQueryResultType
from piltover.db.models import User, Peer, UserPassword, CallbackQuery, InlineQuery, File, InlineQueryResultItem, \
    MessageRef
from piltover.db.models.inline_query_result import InlineQueryResult
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, InvalidConstructorException
from piltover.tl import KeyboardButtonCallback, ReplyInlineMarkup, InputPeerEmpty, InputBotInlineResult, \
    InputBotInlineMessageText, objects, InputBotInlineMessageMediaAuto, \
    InputBotInlineResultPhoto, InputBotInlineResultDocument, InputPhoto, InputDocument
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

    if (message := await MessageRef.get_(request.msg_id, peer)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if not message.content.author.bot:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    builtin_bot = message.content.author.system

    kbd = message.content.make_reply_markup()
    if kbd is None or not isinstance(kbd, ReplyInlineMarkup):
        raise ErrorRpc(error_code=400, error_message="DATA_INVALID")

    message_for_bot = None
    if not builtin_bot and (message_for_bot := await message.get_for_user(message.content.author)) is None:
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
        await upd.bot_callback_query(message_for_bot.content.author, query)

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
            message__content__author=user, id=request.query_id,
            created_at__gte=datetime.now(UTC) - timedelta(seconds=15),
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

    cached = await InlineQueryResult.filter(
        Q(query__user=user, private=True) | Q(private=False),
        query__query=request.query,
        query__offset=request.offset[:64],
        query__bot=bot,
        query__inline_peer=query_peer,
        cache_until__gte=datetime.now(UTC),
    ).order_by("-id").first()

    if cached is not None:
        return await cached.to_tl()

    inline_query = InlineQuery(
        user=user,
        bot=bot.user,
        query=request.query[:128],
        offset=request.offset[:64],
        inline_peer=query_peer,
    )

    if bot.user.system:
        resp = await process_inline_query(inline_query)
        if resp is None:
            raise ErrorRpc(error_code=400, error_message="BOT_RESPONSE_TIMEOUT")

        result, items = resp
        async with in_transaction():
            await inline_query.save()
            result.query = inline_query
            await result.save()
            for item in items:
                item.result = result
            if items:
                await InlineQueryResultItem.bulk_create(items)

        return await result.to_tl(items)
    else:
        ctx = request_ctx.get()
        pubsub = ctx.worker.pubsub

        await inline_query.save()

        topic = f"bot-inline-query/{inline_query.id}"
        await pubsub.listen(topic, None)
        await upd.bot_inline_query(bot.user, inline_query)

        result = await pubsub.listen(topic, 15)
        if result is None:
            await inline_query.delete()
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

    # TODO: validate request.gallery ?

    async with in_transaction():
        query = await InlineQuery.select_for_update(no_key=True).get_or_none(
            id=request.query_id, bot=user, created_at__gte=datetime.now(UTC) - timedelta(seconds=15),
        )
        if query is None:
            raise ErrorRpc(error_code=400, error_message="QUERY_ID_INVALID")

        result_items = []
        for result in request.results:
            if not isinstance(result, (InputBotInlineResult, InputBotInlineResultPhoto, InputBotInlineResultDocument)):
                raise ErrorRpc(error_code=400, error_message="RESULT_TYPE_INVALID")

            type_ = result.type_.lower()
            if type_ not in InlineQueryResultType._value2member_map_:
                raise ErrorRpc(error_code=400, error_message="RESULT_TYPE_INVALID")

            result_type = InlineQueryResultType(type_)

            # TODO: validate that at least media or text is not empty

            item = InlineQueryResultItem(position=len(result_items))
            result_items.append(item)

            message = result.send_message
            if isinstance(message, InputBotInlineMessageText):
                item.send_message_no_webpage = message.no_webpage
                item.send_message_invert_media = message.invert_media
                item.send_message_text = message.message
                item.send_message_entities = await process_message_entities(message.message, message.entities, user)
            elif isinstance(message, InputBotInlineMessageMediaAuto):
                item.send_message_invert_media = message.invert_media
                item.send_message_text = message.message
                item.send_message_entities = await process_message_entities(message.message, message.entities, user)
            else:
                # TODO: InputBotInlineMessageMediaGeo
                # TODO: InputBotInlineMessageMediaVenue
                # TODO: InputBotInlineMessageMediaContact
                # TODO: replace with `Unreachable`
                raise ErrorRpc(error_code=400, error_message="RESULT_TYPE_INVALID")

            if isinstance(result, InputBotInlineResult):
                if result.content is not None:
                    # TODO: download content in worker or return WebDocument
                    raise ErrorRpc(error_code=501, error_message="NOT_IMPLEMENTED")

                item.item_id = result.id
                item.type = result_type
                item.title = result.title
                item.description = result.description
                item.url = result.url
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

                item.item_id = result.id
                item.type = result_type
                item.photo = photo
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

                item.item_id = result.id
                item.type = result_type
                item.document = doc
                item.title = result.title
                item.description = result.description

        bot_result = BotResults(
            query_id=request.query_id,
            results=[item.to_tl() for item in result_items],
            cache_time=cache_time,
            users=[],
            gallery=request.gallery,
            next_offset=request.next_offset[:64] if request.next_offset is not None else None,
            switch_pm=None,  # TODO: implement switch_pm
            switch_webview=None,
        ).write()

        if cache_time:
            async with in_transaction():
                query = await InlineQueryResult.create(
                    query=query,
                    next_offset=request.next_offset[:64] if request.next_offset is not None else None,
                    cache_time=cache_time,
                    cache_until=datetime.now(UTC) + timedelta(seconds=cache_time),
                    gallery=request.gallery,
                    private=request.private,
                )
                for item in result_items:
                    item.query = item
                if result_items:
                    await InlineQueryResultItem.bulk_create(result_items)

        await ctx.worker.pubsub.notify(
            topic=f"bot-inline-query/{query.id}",
            data=bot_result,
        )

    return True

