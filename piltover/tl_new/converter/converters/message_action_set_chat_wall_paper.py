from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import MessageActionSetChatWallPaper, MessageActionSetChatWallPaper_158


class MessageActionSetChatWallPaperConverter(ConverterBase):
    base = MessageActionSetChatWallPaper
    old = [MessageActionSetChatWallPaper_158]
    layers = [158]

    @staticmethod
    def from_158(obj: MessageActionSetChatWallPaper_158) -> MessageActionSetChatWallPaper:
        data = obj.to_dict()
        return MessageActionSetChatWallPaper(**data)

    @staticmethod
    def to_158(obj: MessageActionSetChatWallPaper) -> MessageActionSetChatWallPaper_158:
        data = obj.to_dict()
        del data["for_both"]
        del data["same"]
        del data["flags"]
        return MessageActionSetChatWallPaper_158(**data)
