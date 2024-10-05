from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import RequestSimpleWebView, RequestSimpleWebView_140, RequestSimpleWebView_145


class RequestSimpleWebViewConverter(ConverterBase):
    base = RequestSimpleWebView
    old = [RequestSimpleWebView_140, RequestSimpleWebView_145]
    layers = [140, 145]

    @staticmethod
    def from_140(obj: RequestSimpleWebView_140) -> RequestSimpleWebView:
        data = obj.to_dict()
        data["platform"] = "linux"
        return RequestSimpleWebView(**data)

    @staticmethod
    def to_140(obj: RequestSimpleWebView) -> RequestSimpleWebView_140:
        data = obj.to_dict()
        del data["platform"]
        del data["from_switch_webview"]
        del data["start_param"]
        del data["from_side_menu"]
        if data["url"] is None:
            data["url"] = ""
        return RequestSimpleWebView_140(**data)

    @staticmethod
    def from_145(obj: RequestSimpleWebView_145) -> RequestSimpleWebView:
        data = obj.to_dict()
        return RequestSimpleWebView(**data)

    @staticmethod
    def to_145(obj: RequestSimpleWebView) -> RequestSimpleWebView_145:
        data = obj.to_dict()
        del data["from_switch_webview"]
        del data["from_side_menu"]
        del data["start_param"]
        if data["url"] is None:
            data["url"] = ""
        return RequestSimpleWebView_145(**data)
