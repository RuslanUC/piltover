from piltover.tl_new.functions.messages import RequestSimpleWebView, RequestSimpleWebView_140, RequestSimpleWebView_145
from piltover.tl_new.converter import ConverterBase


class RequestSimpleWebViewConverter(ConverterBase):
    base = RequestSimpleWebView
    old = [RequestSimpleWebView_140, RequestSimpleWebView_145]
    layers = [140, 145]

    @staticmethod
    def from_140(obj: RequestSimpleWebView_140) -> RequestSimpleWebView:
        data = obj.to_dict()
        assert False, "required field 'platform' added in base tl object"  # TODO: add field
        assert False, "type of field 'url' changed (string -> flags.3?string)"  # TODO: type changed
        return RequestSimpleWebView(**data)

    @staticmethod
    def to_140(obj: RequestSimpleWebView) -> RequestSimpleWebView_140:
        data = obj.to_dict()
        del data["platform"]
        del data["from_switch_webview"]
        del data["start_param"]
        del data["from_side_menu"]
        assert False, "type of field 'url' changed (flags.3?string -> string)"  # TODO: type changed
        return RequestSimpleWebView_140(**data)

    @staticmethod
    def from_145(obj: RequestSimpleWebView_145) -> RequestSimpleWebView:
        data = obj.to_dict()
        assert False, "type of field 'url' changed (string -> flags.3?string)"  # TODO: type changed
        return RequestSimpleWebView(**data)

    @staticmethod
    def to_145(obj: RequestSimpleWebView) -> RequestSimpleWebView_145:
        data = obj.to_dict()
        del data["from_switch_webview"]
        del data["from_side_menu"]
        del data["start_param"]
        assert False, "type of field 'url' changed (flags.3?string -> string)"  # TODO: type changed
        return RequestSimpleWebView_145(**data)

