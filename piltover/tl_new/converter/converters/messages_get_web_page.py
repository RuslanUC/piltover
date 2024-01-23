from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.messages import GetWebPage, GetWebPage_136


class GetWebPageConverter(ConverterBase):
    base = GetWebPage
    old = [GetWebPage_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetWebPage_136) -> GetWebPage:
        data = obj.to_dict()
        return GetWebPage(**data)

    @staticmethod
    def to_136(obj: GetWebPage) -> GetWebPage_136:
        data = obj.to_dict()
        return GetWebPage_136(**data)
