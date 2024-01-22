from piltover.tl_new.functions.messages import RequestWebView, RequestWebView_140, RequestWebView_143, RequestWebView_145, RequestWebView_148
from piltover.tl_new.converter import ConverterBase


class RequestWebViewConverter(ConverterBase):
    base = RequestWebView
    old = [RequestWebView_140, RequestWebView_143, RequestWebView_145, RequestWebView_148]
    layers = [140, 143, 145, 148]

    @staticmethod
    def from_140(obj: RequestWebView_140) -> RequestWebView:
        data = obj.to_dict()
        assert False, "required field 'platform' added in base tl object"  # TODO: add field
        del data["reply_to_msg_id"]
        return RequestWebView(**data)

    @staticmethod
    def to_140(obj: RequestWebView) -> RequestWebView_140:
        data = obj.to_dict()
        del data["send_as"]
        del data["platform"]
        del data["reply_to"]
        return RequestWebView_140(**data)

    @staticmethod
    def from_143(obj: RequestWebView_143) -> RequestWebView:
        data = obj.to_dict()
        assert False, "required field 'platform' added in base tl object"  # TODO: add field
        del data["reply_to_msg_id"]
        return RequestWebView(**data)

    @staticmethod
    def to_143(obj: RequestWebView) -> RequestWebView_143:
        data = obj.to_dict()
        del data["platform"]
        del data["reply_to"]
        return RequestWebView_143(**data)

    @staticmethod
    def from_145(obj: RequestWebView_145) -> RequestWebView:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return RequestWebView(**data)

    @staticmethod
    def to_145(obj: RequestWebView) -> RequestWebView_145:
        data = obj.to_dict()
        del data["reply_to"]
        return RequestWebView_145(**data)

    @staticmethod
    def from_148(obj: RequestWebView_148) -> RequestWebView:
        data = obj.to_dict()
        del data["top_msg_id"]
        del data["reply_to_msg_id"]
        return RequestWebView(**data)

    @staticmethod
    def to_148(obj: RequestWebView) -> RequestWebView_148:
        data = obj.to_dict()
        del data["reply_to"]
        return RequestWebView_148(**data)

