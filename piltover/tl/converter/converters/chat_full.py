from piltover.tl import ChatReactionsSome, ReactionEmoji
from piltover.tl.converter import ConverterBase
from piltover.tl.types import ChatFull, ChatFull_136


class ChatFullConverter(ConverterBase):
    base = ChatFull
    old = [ChatFull_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ChatFull_136) -> ChatFull:
        data = obj.to_dict()
        if data["available_reactions"] is not None:
            data["new_value"] = ChatReactionsSome(
                reactions=[ReactionEmoji(emoticon=reaction) for reaction in obj.available_reactions]
            )
        return ChatFull(**data)

    @staticmethod
    def to_136(obj: ChatFull) -> ChatFull_136:
        data = obj.to_dict()
        del data["translations_disabled"]
        if isinstance(obj.available_reactions, ChatReactionsSome):
            data["new_value"] = [
                reaction.emoticon for reaction in obj.available_reactions.reactions
                if isinstance(reaction, ReactionEmoji)
            ]
        return ChatFull_136(**data)
