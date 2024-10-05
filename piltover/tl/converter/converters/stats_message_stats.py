from piltover.tl import StatsGraph, DataJSON
from piltover.tl.converter import ConverterBase
from piltover.tl.types.stats import MessageStats, MessageStats_136


class MessageStatsConverter(ConverterBase):
    base = MessageStats
    old = [MessageStats_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageStats_136) -> MessageStats:
        data = obj.to_dict()
        data["reactions_by_emotion_graph"] = StatsGraph(json=DataJSON(data="{}"))
        return MessageStats(**data)

    @staticmethod
    def to_136(obj: MessageStats) -> MessageStats_136:
        data = obj.to_dict()
        del data["reactions_by_emotion_graph"]
        return MessageStats_136(**data)
