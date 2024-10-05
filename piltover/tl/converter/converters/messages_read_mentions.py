from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import ReadMentions, ReadMentions_136


class ReadMentionsConverter(ConverterBase):
    base = ReadMentions
    old = [ReadMentions_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ReadMentions_136) -> ReadMentions:
        data = obj.to_dict()
        return ReadMentions(**data)

    @staticmethod
    def to_136(obj: ReadMentions) -> ReadMentions_136:
        data = obj.to_dict()
        del data["flags"]
        del data["top_msg_id"]
        return ReadMentions_136(**data)
