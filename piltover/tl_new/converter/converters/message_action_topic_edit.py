from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import MessageActionTopicEdit, MessageActionTopicEdit_148


class MessageActionTopicEditConverter(ConverterBase):
    base = MessageActionTopicEdit
    old = [MessageActionTopicEdit_148]
    layers = [148]

    @staticmethod
    def from_148(obj: MessageActionTopicEdit_148) -> MessageActionTopicEdit:
        data = obj.to_dict()
        return MessageActionTopicEdit(**data)

    @staticmethod
    def to_148(obj: MessageActionTopicEdit) -> MessageActionTopicEdit_148:
        data = obj.to_dict()
        del data["hidden"]
        return MessageActionTopicEdit_148(**data)
