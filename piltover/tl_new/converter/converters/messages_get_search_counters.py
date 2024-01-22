from piltover.tl_new.functions.messages import GetSearchCounters, GetSearchCounters_136
from piltover.tl_new.converter import ConverterBase


class GetSearchCountersConverter(ConverterBase):
    base = GetSearchCounters
    old = [GetSearchCounters_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetSearchCounters_136) -> GetSearchCounters:
        data = obj.to_dict()
        return GetSearchCounters(**data)

    @staticmethod
    def to_136(obj: GetSearchCounters) -> GetSearchCounters_136:
        data = obj.to_dict()
        del data["flags"]
        del data["top_msg_id"]
        return GetSearchCounters_136(**data)

