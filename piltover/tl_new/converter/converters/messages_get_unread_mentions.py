from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.messages import GetUnreadMentions, GetUnreadMentions_136


class GetUnreadMentionsConverter(ConverterBase):
    base = GetUnreadMentions
    old = [GetUnreadMentions_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetUnreadMentions_136) -> GetUnreadMentions:
        data = obj.to_dict()
        return GetUnreadMentions(**data)

    @staticmethod
    def to_136(obj: GetUnreadMentions) -> GetUnreadMentions_136:
        data = obj.to_dict()
        del data["flags"]
        del data["top_msg_id"]
        return GetUnreadMentions_136(**data)
