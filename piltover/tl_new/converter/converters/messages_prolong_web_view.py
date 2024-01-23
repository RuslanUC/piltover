from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.messages import ProlongWebView, ProlongWebView_140, ProlongWebView_143, \
    ProlongWebView_148


class ProlongWebViewConverter(ConverterBase):
    base = ProlongWebView
    old = [ProlongWebView_140, ProlongWebView_143, ProlongWebView_148]
    layers = [140, 143, 148]

    @staticmethod
    def from_140(obj: ProlongWebView_140) -> ProlongWebView:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return ProlongWebView(**data)

    @staticmethod
    def to_140(obj: ProlongWebView) -> ProlongWebView_140:
        data = obj.to_dict()
        del data["send_as"]
        del data["reply_to"]
        return ProlongWebView_140(**data)

    @staticmethod
    def from_143(obj: ProlongWebView_143) -> ProlongWebView:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return ProlongWebView(**data)

    @staticmethod
    def to_143(obj: ProlongWebView) -> ProlongWebView_143:
        data = obj.to_dict()
        del data["reply_to"]
        return ProlongWebView_143(**data)

    @staticmethod
    def from_148(obj: ProlongWebView_148) -> ProlongWebView:
        data = obj.to_dict()
        del data["top_msg_id"]
        del data["reply_to_msg_id"]
        return ProlongWebView(**data)

    @staticmethod
    def to_148(obj: ProlongWebView) -> ProlongWebView_148:
        data = obj.to_dict()
        del data["reply_to"]
        return ProlongWebView_148(**data)
