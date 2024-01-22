from piltover.tl_new.functions.messages import SendInlineBotResult, SendInlineBotResult_136, SendInlineBotResult_148
from piltover.tl_new.converter import ConverterBase


class SendInlineBotResultConverter(ConverterBase):
    base = SendInlineBotResult
    old = [SendInlineBotResult_136, SendInlineBotResult_148]
    layers = [136, 148]

    @staticmethod
    def from_136(obj: SendInlineBotResult_136) -> SendInlineBotResult:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return SendInlineBotResult(**data)

    @staticmethod
    def to_136(obj: SendInlineBotResult) -> SendInlineBotResult_136:
        data = obj.to_dict()
        del data["reply_to"]
        return SendInlineBotResult_136(**data)

    @staticmethod
    def from_148(obj: SendInlineBotResult_148) -> SendInlineBotResult:
        data = obj.to_dict()
        del data["top_msg_id"]
        del data["reply_to_msg_id"]
        return SendInlineBotResult(**data)

    @staticmethod
    def to_148(obj: SendInlineBotResult) -> SendInlineBotResult_148:
        data = obj.to_dict()
        del data["reply_to"]
        return SendInlineBotResult_148(**data)

