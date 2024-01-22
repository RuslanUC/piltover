from piltover.tl_new.functions.updates import GetDifference, GetDifference_136
from piltover.tl_new.converter import ConverterBase


class GetDifferenceConverter(ConverterBase):
    base = GetDifference
    old = [GetDifference_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetDifference_136) -> GetDifference:
        data = obj.to_dict()
        return GetDifference(**data)

    @staticmethod
    def to_136(obj: GetDifference) -> GetDifference_136:
        data = obj.to_dict()
        del data["pts_limit"]
        del data["qts_limit"]
        return GetDifference_136(**data)

