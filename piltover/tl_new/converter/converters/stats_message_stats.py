from piltover.tl_new.types.stats import MessageStats, MessageStats_136
from piltover.tl_new.converter import ConverterBase


class MessageStatsConverter(ConverterBase):
    base = MessageStats
    old = [MessageStats_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageStats_136) -> MessageStats:
        data = obj.to_dict()
        assert False, "required field 'reactions_by_emotion_graph' added in base tl object"  # TODO: add field
        return MessageStats(**data)

    @staticmethod
    def to_136(obj: MessageStats) -> MessageStats_136:
        data = obj.to_dict()
        del data["reactions_by_emotion_graph"]
        return MessageStats_136(**data)

