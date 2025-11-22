from datetime import datetime

from pytz import UTC
from tortoise.expressions import Q, Subquery

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.history import format_messages_internal, get_messages_query_internal
from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import PeerType, ChatBannedRights
from piltover.db.models import Reaction, User, Message, Peer, MessageReaction, ReadState, State, RecentReaction, \
    UserReactionsSettings
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import ReactionEmoji, ReactionCustomEmoji, Updates
from piltover.tl.functions.messages import GetAvailableReactions, SendReaction, SetDefaultReaction, \
    GetMessagesReactions, GetUnreadReactions, ReadReactions, GetRecentReactions, ClearRecentReactions
from piltover.tl.types.messages import AvailableReactions, Messages, AffectedHistory, Reactions, ReactionsNotModified, \
    AvailableReactionsNotModified
from piltover.worker import MessageHandler

handler = MessageHandler("messages.reactions")


@handler.on_request(GetAvailableReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_available_reactions(request: GetAvailableReactions) -> AvailableReactions | AvailableReactionsNotModified:
    ids = await Reaction.all().order_by("id").values_list("id", flat=True)

    reactions_hash = telegram_hash(ids, 32)
    if reactions_hash == request.hash:
        return AvailableReactionsNotModified()

    return AvailableReactions(
        hash=reactions_hash,
        reactions=[
            reaction.to_tl_available_reaction()
            for reaction in await Reaction.all().select_related(
                "static_icon", "appear_animation", "select_animation", "activate_animation", "effect_animation",
                "around_animation", "center_icon",
            )
        ]
    )


@handler.on_request(SendReaction)
async def send_reaction(request: SendReaction, user: User) -> Updates:
    reaction = None
    if request.reaction:
        if isinstance(request.reaction[0], ReactionEmoji):
            reaction = await Reaction.get_or_none(Reaction.q_from_reaction(request.reaction[0].emoticon))
        elif isinstance(request.reaction[0], ReactionCustomEmoji):
            raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")

    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
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

    existing_reaction = await MessageReaction.get_or_none(user=user, message=message)
    if (existing_reaction is None and reaction is None) \
            or (existing_reaction is not None and reaction is not None and existing_reaction.reaction_id == reaction.id):
        raise ErrorRpc(error_code=400, error_message="MESSAGE_NOT_MODIFIED")

    messages: dict[Peer, Message] = {}

    if peer.type is not PeerType.CHANNEL:
        for opp_message in await Message.filter(internal_id=message.internal_id).select_related("peer", "peer__owner"):
            messages[opp_message.peer] = opp_message

    if existing_reaction is not None:
        if peer.type is PeerType.CHANNEL:
            await existing_reaction.delete()
        else:
            reactions_q = MessageReaction.filter(
                user=user, message__internal_id=message.internal_id,
            ).values_list("id", flat=True)
            await MessageReaction.filter(id__in=Subquery(reactions_q)).delete()

    if reaction is not None:
        if peer.type is PeerType.CHANNEL:
            # TODO: send update to message author
            await MessageReaction.create(user=user, message=message, reaction=reaction)
            return await upd.update_reactions(user, [message], peer)

        reactions_to_create = []
        for opp_message in messages.values():
            reactions_to_create.append(MessageReaction(user=user, message=opp_message, reaction=reaction))

        await MessageReaction.bulk_create(reactions_to_create)

    result = await upd.update_reactions(user, [message], peer)

    for opp_peer, opp_message in messages.items():
        if opp_peer.owner == user:
            continue
        await upd.update_reactions(opp_peer.owner, [opp_message], opp_peer)

    if reaction is not None and request.add_to_recent:
        await RecentReaction.update_time_or_create(user, reaction, datetime.now(UTC))
        await upd.update_recent_reactions(user)

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
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.VIEW_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")

    if (messages := await Message.get_many(request.id, peer)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    return await upd.update_reactions(user, messages, peer, False)


@handler.on_request(GetUnreadReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_unread_reactions(request: GetUnreadReactions, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    read_state, _ = await ReadState.get_or_create(peer=peer)

    query = await get_messages_query_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset, user.id,
        after_reaction_id=read_state.last_reaction_id,
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
    read_state, _ = await ReadState.get_or_create(peer=peer)

    reaction_query = Q(message__author=user) & (
        Q(message__peer__owner=user, message__peer__channel__id=peer.channel_id)
        if peer.type is PeerType.CHANNEL
        else Q(message__peer=peer)
    )
    new_last_reaction_id = await MessageReaction.filter(reaction_query).order_by("-id").first().values_list("id", flat=True)
    new_last_reaction_id = new_last_reaction_id or read_state.last_reaction_id

    pts = await State.add_pts(user, 0)

    if new_last_reaction_id == read_state.last_reaction_id:
        return AffectedHistory(
            pts=pts,
            pts_count=0,
            offset=0,
        )

    await ReadState.filter(id=read_state.id).update(last_reaction_id=new_last_reaction_id)

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
            ReactionEmoji(emoticon=reaction.reaction.reaction)
            for reaction in reactions
        ]
    )


@handler.on_request(ClearRecentReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def clear_recent_reactions(user: User) -> bool:
    if await RecentReaction.filter(user=user).exists():
        await RecentReaction.filter(user=user).delete()
        await upd.update_recent_reactions(user)

    return True


# TODO: GetMessageReactionsList
