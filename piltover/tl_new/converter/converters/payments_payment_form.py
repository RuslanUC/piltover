from piltover.tl_new.types.payments import PaymentForm, PaymentForm_136, PaymentForm_143
from piltover.tl_new.converter import ConverterBase


class PaymentFormConverter(ConverterBase):
    base = PaymentForm
    old = [PaymentForm_136, PaymentForm_143]
    layers = [136, 143]

    @staticmethod
    def from_136(obj: PaymentForm_136) -> PaymentForm:
        data = obj.to_dict()
        assert False, "required field 'title' added in base tl object"  # TODO: add field
        assert False, "required field 'description' added in base tl object"  # TODO: add field
        assert False, "type of field 'saved_credentials' changed (flags.1?PaymentSavedCredentials -> flags.1?Vector<PaymentSavedCredentials>)"  # TODO: type changed
        return PaymentForm(**data)

    @staticmethod
    def to_136(obj: PaymentForm) -> PaymentForm_136:
        data = obj.to_dict()
        del data["photo"]
        del data["additional_methods"]
        del data["title"]
        del data["description"]
        assert False, "type of field 'saved_credentials' changed (flags.1?Vector<PaymentSavedCredentials> -> flags.1?PaymentSavedCredentials)"  # TODO: type changed
        return PaymentForm_136(**data)

    @staticmethod
    def from_143(obj: PaymentForm_143) -> PaymentForm:
        data = obj.to_dict()
        assert False, "type of field 'saved_credentials' changed (flags.1?PaymentSavedCredentials -> flags.1?Vector<PaymentSavedCredentials>)"  # TODO: type changed
        return PaymentForm(**data)

    @staticmethod
    def to_143(obj: PaymentForm) -> PaymentForm_143:
        data = obj.to_dict()
        del data["additional_methods"]
        assert False, "type of field 'saved_credentials' changed (flags.1?Vector<PaymentSavedCredentials> -> flags.1?PaymentSavedCredentials)"  # TODO: type changed
        return PaymentForm_143(**data)

