from piltover.tl import InputInvoiceMessage, InputPeerEmpty
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.payments import SendPaymentForm, SendPaymentForm_136


class SendPaymentFormConverter(ConverterBase):
    base = SendPaymentForm
    old = [SendPaymentForm_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SendPaymentForm_136) -> SendPaymentForm:
        data = obj.to_dict()
        data["invoice"] = InputInvoiceMessage(peer=obj.peer, msg_id=obj.msg_id)
        del data["msg_id"]
        del data["peer"]
        return SendPaymentForm(**data)

    @staticmethod
    def to_136(obj: SendPaymentForm) -> SendPaymentForm_136:
        data = obj.to_dict()
        del data["invoice"]
        data["msg_id"] = obj.invoice.msg_id
        data["peer"] = InputPeerEmpty()
        return SendPaymentForm_136(**data)
