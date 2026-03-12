from datetime import datetime

from pytz import UTC
from tortoise.expressions import Q, Subquery, F

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.history import format_messages_internal, get_messages_query_internal
from piltover.app.utils.utils import telegram_hash
from piltover.app_config import AppConfig
from piltover.cache import Cache
from piltover.db.enums import PeerType, FileType
from piltover.db.models import Reaction, User, Peer, MessageReaction, State, RecentReaction, UserReactionsSettings, \
    MessageRef, AvailableChannelReaction, File, MessageContent
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import ReactionEmoji, ReactionCustomEmoji, Updates, ReactionEmpty
from piltover.tl.functions.messages import GetAvailableReactions, SendReaction, SetDefaultReaction, \
    GetMessagesReactions, GetUnreadReactions, ReadReactions, GetRecentReactions, ClearRecentReactions, \
    GetMessageReactionsList
from piltover.tl.types.messages import AvailableReactions, Messages, AffectedHistory, Reactions, ReactionsNotModified, \
    AvailableReactionsNotModified, MessageReactionsList
from piltover.worker import MessageHandler

handler = MessageHandler("messages.reactions")


@handler.on_request(GetAvailableReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_available_reactions(request: GetAvailableReactions) -> AvailableReactions | AvailableReactionsNotModified:
    ids = await Reaction.all().order_by("id").values_list("id", flat=True)

    reactions_hash = telegram_hash(ids, 32)
    if reactions_hash == request.hash:
        return AvailableReactionsNotModified()

    cached = await Cache.obj.get(f"reactions-{reactions_hash}")
    if cached is not None:
        return cached

    result = AvailableReactions(
        hash=reactions_hash,
        reactions=[
            reaction.to_tl_available_reaction()
            for reaction in await Reaction.all().select_related(
                "static_icon", "appear_animation", "select_animation", "activate_animation", "effect_animation",
                "around_animation", "center_icon",
            )
        ]
    )

    await Cache.obj.set(f"reactions-{reactions_hash}", result)
    return result


REACTION_NOT_MODIFIED = ErrorRpc(error_code=400, error_message="MESSAGE_NOT_MODIFIED")


@handler.on_request(SendReaction)
async def send_reaction(request: SendReaction, user: User) -> Updates:
    reaction = None
    custom_reaction = None
    if request.reaction:
        if isinstance(request.reaction[0], ReactionEmoji):
            reaction = await Reaction.get_or_none(Reaction.q_from_reaction(request.reaction[0].emoticon))
        elif isinstance(request.reaction[0], ReactionCustomEmoji):
            custom_reaction = await File.get_or_none(id=request.reaction[0].document_id, type=FileType.DOCUMENT_EMOJI)
            if custom_reaction is None:
                raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")
        elif isinstance(request.reaction[0], ReactionEmpty):
            ...
        else:
            raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")

    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        # TODO: check if this is correct permission
        if not chat_or_channel.can_view_messages(participant):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN", reason="can't view messages")
        channel_min_id = 0
        if peer.type is PeerType.CHANNEL \
                and (channel_min_id := peer.channel.min_id(participant)) is not None \
                and request.msg_id < channel_min_id:
            raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if (message := await MessageRef.get_(request.msg_id, peer, prefetch=("peer__channel",))) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if peer.type is PeerType.CHANNEL and not peer.channel.all_reactions:
        if reaction is None:
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN", reason="custom are disabled")
        if not await AvailableChannelReaction.filter(channel=peer.channel, reaction=reaction).exists():
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN", reason="reaction is disabled 1")
    elif peer.type is PeerType.CHANNEL \
            and peer.channel.all_reactions \
            and not peer.channel.all_reactions_custom \
            and custom_reaction is not None:
        raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN", reason="reaction is disabled 2")

    uniq_reactions = len(await MessageReaction.filter(
        message_id=message.content_id,
    ).distinct().values_list("reaction_id", "custom_emoji_id"))
    if uniq_reactions > AppConfig.REACTIONS_UNIQ_MAX:
        raise ErrorRpc(error_code=400, error_message="REACTIONS_TOO_MANY")

    existing_reaction = await MessageReaction.get_or_none(user=user, message_id=message.content_id)
    if existing_reaction is None and reaction is None and custom_reaction is None:
        raise REACTION_NOT_MODIFIED
    if existing_reaction is not None:
        if reaction is not None and existing_reaction.reaction_id == reaction.id:
            raise REACTION_NOT_MODIFIED
        if custom_reaction is not None and existing_reaction.custom_emoji_id == custom_reaction.id:
            raise REACTION_NOT_MODIFIED

    if existing_reaction is not None:
        if peer.type is PeerType.CHANNEL:
            await existing_reaction.delete()
        else:
            reactions_q = MessageReaction.filter(
                user=user, message_id=message.content_id,
            ).values_list("id", flat=True)
            await MessageReaction.filter(id__in=Subquery(reactions_q)).delete()

    author_reactions_unread = F("author_reactions_unread")

    if reaction is not None or custom_reaction is not None:
        await MessageReaction.create(
            user=user,
            message=message.content,
            reaction=reaction,
            custom_emoji=custom_reaction,
        )
        if message.content.author_id != user.id:
            author_reactions_unread = True

    await MessageContent.filter(id=message.content_id).update(
        reactions_version=F("reactions_version") + 1,
        author_reactions_unread=author_reactions_unread,
    )
    await message.content.refresh_from_db(["reactions_version", "author_reactions_unread"])

    result = await upd.update_reactions(user, [message], peer)

    # TODO: if small supergroup - send updates to all participants,
    #  if big supergroup - send updates only to author (+admins?)
    #  if channel - dont send updates at all
    if peer.type is not PeerType.CHANNEL:
        for opp_message in await MessageRef.filter(
            content_id=message.content_id,
        ).select_related("peer", "peer__owner", "content"):
            await upd.update_reactions(opp_message.peer.owner, [opp_message], opp_message.peer)

    if (reaction is not None or custom_reaction is not None) and request.add_to_recent:
        await RecentReaction.update_time_or_create(user, reaction, custom_reaction, datetime.now(UTC))
        recent_updates = await upd.update_recent_reactions(user)
        result.updates.extend(recent_updates.updates)

    return result


@handler.on_request(SetDefaultReaction, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def set_default_reaction(request: SetDefaultReaction, user: User) -> bool:
    if not isinstance(request.reaction, ReactionEmoji):
        raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")

    reaction = await Reaction.get_or_none(Reaction.q_from_reaction(request.reaction.emoticon))
    if reaction is None:
        raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")

    settings, created = await UserReactionsSettings.get_or_create(user=user)
    if reaction.id == settings.default_reaction_id:
        return True

    settings.default_reaction = reaction
    await settings.save(update_fields=["default_reaction_id"])

    await upd.update_config(user)

    return True


@handler.on_request(GetMessagesReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_messages_reactions(request: GetMessagesReactions, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer, allow_migrated_chat=True)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        # TODO: check if this is correct permission
        if not chat_or_channel.can_view_messages(participant):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")

    if (messages := await MessageRef.get_many(request.id, peer, prefetch_fields=("peer__channel",))) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    return await upd.update_reactions(user, messages, peer, False)


@handler.on_request(GetUnreadReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_unread_reactions(request: GetUnreadReactions, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    query = await get_messages_query_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset, user.id,
        unread_reactions=True,
    )

    messages = await query

    if not messages:
        return Messages(messages=[], chats=[], users=[])

    return await format_messages_internal(
        user, messages, allow_slicing=True, peer=peer, offset_id=request.offset_id, query=query, with_reactions=True,
    )


@handler.on_request(ReadReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def read_reactions(request: ReadReactions, user: User) -> AffectedHistory:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    if peer.type is PeerType.CHANNEL:
        peer_query = Q(messagerefs__peer__owner=user, messagerefs__peer__channel_id=peer.channel_id)
    else:
        peer_query = Q(messagerefs__peer=peer)

    await MessageContent.filter(
        id__in=Subquery(MessageContent.filter(peer_query, author_reactions_unread=True, author=user))
    ).update(
        reactions_version=F("reactions_version") + 1,
        author_reactions_unread=False,
    )

    pts = await State.add_pts(user, 0)

    # TODO: UpdateMessageReactions with unread=False

    return AffectedHistory(
        pts=pts,
        pts_count=0,
        offset=0,
    )


@handler.on_request(GetRecentReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_recent_reactions(request: GetRecentReactions, user: User) -> Reactions | ReactionsNotModified:
    limit = min(50, max(1, request.limit))
    ids = await RecentReaction.filter(user=user).limit(limit).order_by("-used_at").values_list("id", flat=True)

    reactions_hash = telegram_hash(ids, 64)

    if reactions_hash == request.hash:
        return ReactionsNotModified()

    reactions = await RecentReaction.filter(id__in=ids).select_related("reaction").order_by("-used_at")

    return Reactions(
        hash=reactions_hash,
        reactions=[
            reaction.to_tl()
            for reaction in reactions
        ]
    )


@handler.on_request(ClearRecentReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def clear_recent_reactions(user: User) -> bool:
    if await RecentReaction.filter(user=user).exists():
        await RecentReaction.filter(user=user).delete()
        await upd.update_recent_reactions(user)

    return True


REACTIONS_LIST_EMPTY = MessageReactionsList(
    count=0,
    reactions=[],
    chats=[],
    users=[],
    next_offset=None,
)


@handler.on_request(GetMessageReactionsList, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_message_reactions_list(request: GetMessageReactionsList, user: User) -> MessageReactionsList:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    can_see_list = (
            peer.type in (PeerType.SELF, PeerType.USER, PeerType.CHAT)
            or peer.type is PeerType.CHANNEL and peer.channel.supergroup
    )
    if not can_see_list:
        raise ErrorRpc(error_code=400, error_message="BROADCAST_FORBIDDEN")

    if (message := await MessageRef.get_(request.id, peer)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if message.content.author_id == user.id:
        is_unread = message.content.author_reactions_unread
    else:
        is_unread = False

    limit = max(1, min(100, request.limit))

    query_simple = MessageReaction.filter(message_id=message.content_id)

    if request.reaction is not None:
        if isinstance(request.reaction, ReactionEmoji):
            query_simple = query_simple.filter(
                reaction__reaction_id=Reaction.reaction_to_uuid(request.reaction.emoticon),
            )
        elif isinstance(request.reaction, ReactionCustomEmoji):
            query_simple = query_simple.filter(custom_emoji_id=request.reaction.document_id)
        elif isinstance(request.reaction, ReactionEmpty):
            ...
        else:
            return REACTIONS_LIST_EMPTY

    query = query_simple.order_by("-date").limit(limit + 1).select_related("reaction", "user")

    if request.offset is not None:
        try:
            offset_id = int(request.offset)
            if offset_id.bit_length() > 63:
                raise ValueError
        except ValueError:
            ...
        else:
            query = query.filter(id__lte=offset_id)

    reactions = await query
    next_offset = None

    if len(reactions) > limit:
        next_offset = str(reactions.pop().id)

    users = {}
    peer_reactions = []
    for reaction in reactions:
        users[reaction.user_id] = reaction.user
        peer_reactions.append(reaction.to_tl_peer_reaction(user.id, is_unread))

    return MessageReactionsList(
        count=await query_simple.count(),
        reactions=peer_reactions,
        chats=[],
        users=await User.to_tl_bulk(users.values()),
        next_offset=next_offset,
    )
