from piltover.tl_new.functions.payments import SendPaymentForm, SendPaymentForm_136
from piltover.tl_new.converter import ConverterBase


class SendPaymentFormConverter(ConverterBase):
    base = SendPaymentForm
    old = [SendPaymentForm_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SendPaymentForm_136) -> SendPaymentForm:
        data = obj.to_dict()
        assert False, "required field 'invoice' added in base tl object"  # TODO: add field
        del data["msg_id"]
        del data["peer"]
        return SendPaymentForm(**data)

    @staticmethod
    def to_136(obj: SendPaymentForm) -> SendPaymentForm_136:
        data = obj.to_dict()
        del data["invoice"]
        assert False, "required field 'msg_id' deleted in base tl object"  # TODO: delete field
        assert False, "required field 'peer' deleted in base tl object"  # TODO: delete field
        return SendPaymentForm_136(**data)

