from piltover.tl_new.functions.messages import SetChatAvailableReactions, SetChatAvailableReactions_136
from piltover.tl_new.converter import ConverterBase


class SetChatAvailableReactionsConverter(ConverterBase):
    base = SetChatAvailableReactions
    old = [SetChatAvailableReactions_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SetChatAvailableReactions_136) -> SetChatAvailableReactions:
        data = obj.to_dict()
        assert False, "type of field 'available_reactions' changed (Vector<string> -> ChatReactions)"  # TODO: type changed
        return SetChatAvailableReactions(**data)

    @staticmethod
    def to_136(obj: SetChatAvailableReactions) -> SetChatAvailableReactions_136:
        data = obj.to_dict()
        assert False, "type of field 'available_reactions' changed (ChatReactions -> Vector<string>)"  # TODO: type changed
        return SetChatAvailableReactions_136(**data)

