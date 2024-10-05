from piltover.tl.converter import ConverterBase
from piltover.tl.types import ChatInvite, ChatInvite_136


class ChatInviteConverter(ConverterBase):
    base = ChatInvite
    old = [ChatInvite_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ChatInvite_136) -> ChatInvite:
        data = obj.to_dict()
        data["color"] = 0
        return ChatInvite(**data)

    @staticmethod
    def to_136(obj: ChatInvite) -> ChatInvite_136:
        data = obj.to_dict()
        del data["color"]
        return ChatInvite_136(**data)
