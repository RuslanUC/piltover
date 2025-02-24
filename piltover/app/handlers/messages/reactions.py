from piltover.tl.functions.messages import GetAvailableReactions
from piltover.tl.types.messages import AvailableReactions
from piltover.worker import MessageHandler

handler = MessageHandler("messages.reactions")


# noinspection PyUnusedLocal
@handler.on_request(GetAvailableReactions)
async def get_available_reactions(request: GetAvailableReactions):  # pragma: no cover
    return AvailableReactions(hash=0, reactions=[])
