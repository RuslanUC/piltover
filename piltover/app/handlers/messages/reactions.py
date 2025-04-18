from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType, ChatBannedRights
from piltover.db.models import Reaction, User, Message, Peer, MessageReaction
from piltover.exceptions import ErrorRpc
from piltover.tl import ReactionEmoji, ReactionCustomEmoji
from piltover.tl.functions.messages import GetAvailableReactions, SendReaction
from piltover.tl.types.messages import AvailableReactions
from piltover.worker import MessageHandler

handler = MessageHandler("messages.reactions")


@handler.on_request(GetAvailableReactions)
async def get_available_reactions(user: User) -> AvailableReactions:
    reaction: Reaction

    return AvailableReactions(
        hash=1,
        reactions=[
            await reaction.to_tl_available_reaction(user)
            async for reaction in Reaction.all().select_related(
                "static_icon", "appear_animation", "select_animation", "activate_animation", "effect_animation",
                "around_animation", "center_icon",
            )
        ]
    )


@handler.on_request(SendReaction)
async def send_reaction(request: SendReaction, user: User) -> ...:
    # TODO: request.add_to_recent

    reaction = None
    if request.reaction:
        if isinstance(request.reaction[0], ReactionEmoji):
            reaction = await Reaction.get_or_none(reaction=request.reaction[0].emoticon)
        elif isinstance(request.reaction[0], ReactionCustomEmoji):
            raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")

    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        chat_or_channel = peer.chat_or_channel
        participant = await chat_or_channel.get_participant_raise(user)
        # TODO: check if this is correct right
        if not chat_or_channel.user_has_permission(participant, ChatBannedRights.VIEW_MESSAGES):
            raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")

    if (message := await Message.get_(request.msg_id, peer)) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    existing_reaction = await MessageReaction.get_or_none(user=user, message=message)
    if (existing_reaction is None and reaction is None) \
            or (existing_reaction is not None and reaction is not None and existing_reaction.reaction_id == reaction.id):
        raise ErrorRpc(error_code=400, error_message="MESSAGE_NOT_MODIFIED")

    if existing_reaction is not None:
        if peer.type is PeerType.CHANNEL:
            await existing_reaction.delete()
        else:
            await MessageReaction.filter(user=user, message__internal_id=message.internal_id).delete()

    if peer.type is PeerType.CHANNEL:
        await MessageReaction.create(user=user, message=message, reaction=reaction)
        return await UpdatesManager.update_reactions(user, message, peer)

    await MessageReaction.bulk_create([
        MessageReaction(user=user, message=opp_message, reaction=reaction)
        for opp_message in await Message.filter(internal_id=message.internal_id)
    ])

    # TODO: send updates to other users (only to message author?)

    return await UpdatesManager.update_reactions(user, message, peer)

