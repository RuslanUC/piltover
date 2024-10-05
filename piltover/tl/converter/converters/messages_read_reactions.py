from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import ReadReactions, ReadReactions_138


class ReadReactionsConverter(ConverterBase):
    base = ReadReactions
    old = [ReadReactions_138]
    layers = [138]

    @staticmethod
    def from_138(obj: ReadReactions_138) -> ReadReactions:
        data = obj.to_dict()
        return ReadReactions(**data)

    @staticmethod
    def to_138(obj: ReadReactions) -> ReadReactions_138:
        data = obj.to_dict()
        del data["flags"]
        del data["top_msg_id"]
        return ReadReactions_138(**data)
