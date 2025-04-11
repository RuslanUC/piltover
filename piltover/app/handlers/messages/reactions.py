from piltover.db.models import Reaction, User
from piltover.tl.functions.messages import GetAvailableReactions
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
