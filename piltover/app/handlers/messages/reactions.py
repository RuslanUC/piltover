from piltover.tl.functions.messages import GetAvailableReactions
from piltover.tl.types.messages import AvailableReactions
from piltover.worker import MessageHandler

handler = MessageHandler("messages.reactions")


@handler.on_request(GetAvailableReactions)
async def get_available_reactions(request: GetAvailableReactions):
    return AvailableReactions(hash=0, reactions=[])
