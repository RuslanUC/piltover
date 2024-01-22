from piltover.tl_new.types import MessageReactions, MessageReactions_136
from piltover.tl_new.converter import ConverterBase


class MessageReactionsConverter(ConverterBase):
    base = MessageReactions
    old = [MessageReactions_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageReactions_136) -> MessageReactions:
        data = obj.to_dict()
        del data["recent_reactons"]
        return MessageReactions(**data)

    @staticmethod
    def to_136(obj: MessageReactions) -> MessageReactions_136:
        data = obj.to_dict()
        del data["recent_reactions"]
        return MessageReactions_136(**data)

