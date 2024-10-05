from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import GetUnreadReactions, GetUnreadReactions_138


class GetUnreadReactionsConverter(ConverterBase):
    base = GetUnreadReactions
    old = [GetUnreadReactions_138]
    layers = [138]

    @staticmethod
    def from_138(obj: GetUnreadReactions_138) -> GetUnreadReactions:
        data = obj.to_dict()
        return GetUnreadReactions(**data)

    @staticmethod
    def to_138(obj: GetUnreadReactions) -> GetUnreadReactions_138:
        data = obj.to_dict()
        del data["flags"]
        del data["top_msg_id"]
        return GetUnreadReactions_138(**data)
