from piltover.tl import ChatReactionsSome, ReactionEmoji
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import SetChatAvailableReactions, SetChatAvailableReactions_136


class SetChatAvailableReactionsConverter(ConverterBase):
    base = SetChatAvailableReactions
    old = [SetChatAvailableReactions_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SetChatAvailableReactions_136) -> SetChatAvailableReactions:
        data = obj.to_dict()
        data["available_reactions"] = ChatReactionsSome(
            reactions=[ReactionEmoji(emoticon=reaction) for reaction in obj.available_reactions]
        )
        return SetChatAvailableReactions(**data)

    @staticmethod
    def to_136(obj: SetChatAvailableReactions) -> SetChatAvailableReactions_136:
        data = obj.to_dict()
        data["available_reactions"] = []
        if isinstance(obj.available_reactions, ChatReactionsSome):
            data["available_reactions"] = [
                reaction.emoticon for reaction in obj.available_reactions.reactions
                if isinstance(reaction, ReactionEmoji)
            ]
        return SetChatAvailableReactions_136(**data)
