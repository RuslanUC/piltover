from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import Dialog, Dialog_136, Dialog_138


class DialogConverter(ConverterBase):
    base = Dialog
    old = [Dialog_136, Dialog_138]
    layers = [136, 138]

    @staticmethod
    def from_136(obj: Dialog_136) -> Dialog:
        data = obj.to_dict()
        data["unread_reactions_count"] = 0
        return Dialog(**data)

    @staticmethod
    def to_136(obj: Dialog) -> Dialog_136:
        data = obj.to_dict()
        del data["unread_reactions_count"]
        del data["ttl_period"]
        del data["view_forum_as_messages"]
        return Dialog_136(**data)

    @staticmethod
    def from_138(obj: Dialog_138) -> Dialog:
        data = obj.to_dict()
        return Dialog(**data)

    @staticmethod
    def to_138(obj: Dialog) -> Dialog_138:
        data = obj.to_dict()
        del data["ttl_period"]
        del data["view_forum_as_messages"]
        return Dialog_138(**data)
