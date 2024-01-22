from piltover.tl_new.types import WebPageEmpty, WebPageEmpty_136
from piltover.tl_new.converter import ConverterBase


class WebPageEmptyConverter(ConverterBase):
    base = WebPageEmpty
    old = [WebPageEmpty_136]
    layers = [136]

    @staticmethod
    def from_136(obj: WebPageEmpty_136) -> WebPageEmpty:
        data = obj.to_dict()
        return WebPageEmpty(**data)

    @staticmethod
    def to_136(obj: WebPageEmpty) -> WebPageEmpty_136:
        data = obj.to_dict()
        del data["url"]
        del data["flags"]
        return WebPageEmpty_136(**data)

