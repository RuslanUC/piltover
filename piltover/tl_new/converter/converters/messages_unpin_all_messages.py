from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.messages import UnpinAllMessages, UnpinAllMessages_136


class UnpinAllMessagesConverter(ConverterBase):
    base = UnpinAllMessages
    old = [UnpinAllMessages_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UnpinAllMessages_136) -> UnpinAllMessages:
        data = obj.to_dict()
        return UnpinAllMessages(**data)

    @staticmethod
    def to_136(obj: UnpinAllMessages) -> UnpinAllMessages_136:
        data = obj.to_dict()
        del data["flags"]
        del data["top_msg_id"]
        return UnpinAllMessages_136(**data)
