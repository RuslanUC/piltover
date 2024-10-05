from piltover.tl import InputInvoiceMessage, InputPeerEmpty
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.payments import GetPaymentForm, GetPaymentForm_136


class GetPaymentFormConverter(ConverterBase):
    base = GetPaymentForm
    old = [GetPaymentForm_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetPaymentForm_136) -> GetPaymentForm:
        data = obj.to_dict()
        data["invoice"] = InputInvoiceMessage(peer=obj.peer, msg_id=obj.msg_id)
        del data["msg_id"]
        del data["peer"]
        return GetPaymentForm(**data)

    @staticmethod
    def to_136(obj: GetPaymentForm) -> GetPaymentForm_136:
        data = obj.to_dict()
        del data["invoice"]
        data["msg_id"] = obj.invoice.msg_id
        data["peer"] = InputPeerEmpty()
        return GetPaymentForm_136(**data)
