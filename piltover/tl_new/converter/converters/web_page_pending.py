from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import WebPagePending, WebPagePending_136


class WebPagePendingConverter(ConverterBase):
    base = WebPagePending
    old = [WebPagePending_136]
    layers = [136]

    @staticmethod
    def from_136(obj: WebPagePending_136) -> WebPagePending:
        data = obj.to_dict()
        return WebPagePending(**data)

    @staticmethod
    def to_136(obj: WebPagePending) -> WebPagePending_136:
        data = obj.to_dict()
        del data["url"]
        del data["flags"]
        return WebPagePending_136(**data)
