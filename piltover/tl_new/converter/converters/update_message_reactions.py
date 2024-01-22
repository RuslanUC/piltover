from piltover.tl_new.types import UpdateMessageReactions, UpdateMessageReactions_136
from piltover.tl_new.converter import ConverterBase


class UpdateMessageReactionsConverter(ConverterBase):
    base = UpdateMessageReactions
    old = [UpdateMessageReactions_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdateMessageReactions_136) -> UpdateMessageReactions:
        data = obj.to_dict()
        return UpdateMessageReactions(**data)

    @staticmethod
    def to_136(obj: UpdateMessageReactions) -> UpdateMessageReactions_136:
        data = obj.to_dict()
        del data["top_msg_id"]
        del data["flags"]
        return UpdateMessageReactions_136(**data)

