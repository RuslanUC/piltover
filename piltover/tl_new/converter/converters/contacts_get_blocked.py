from piltover.tl_new.functions.contacts import GetBlocked, GetBlocked_136
from piltover.tl_new.converter import ConverterBase


class GetBlockedConverter(ConverterBase):
    base = GetBlocked
    old = [GetBlocked_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetBlocked_136) -> GetBlocked:
        data = obj.to_dict()
        return GetBlocked(**data)

    @staticmethod
    def to_136(obj: GetBlocked) -> GetBlocked_136:
        data = obj.to_dict()
        del data["my_stories_from"]
        del data["flags"]
        return GetBlocked_136(**data)

