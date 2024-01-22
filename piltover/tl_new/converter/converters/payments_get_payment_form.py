from piltover.tl_new.functions.payments import GetPaymentForm, GetPaymentForm_136
from piltover.tl_new.converter import ConverterBase


class GetPaymentFormConverter(ConverterBase):
    base = GetPaymentForm
    old = [GetPaymentForm_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetPaymentForm_136) -> GetPaymentForm:
        data = obj.to_dict()
        assert False, "required field 'invoice' added in base tl object"  # TODO: add field
        del data["msg_id"]
        del data["peer"]
        return GetPaymentForm(**data)

    @staticmethod
    def to_136(obj: GetPaymentForm) -> GetPaymentForm_136:
        data = obj.to_dict()
        del data["invoice"]
        assert False, "required field 'msg_id' deleted in base tl object"  # TODO: delete field
        assert False, "required field 'peer' deleted in base tl object"  # TODO: delete field
        return GetPaymentForm_136(**data)

