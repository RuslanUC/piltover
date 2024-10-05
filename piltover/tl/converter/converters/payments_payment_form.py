from piltover.tl.converter import ConverterBase
from piltover.tl.types.payments import PaymentForm, PaymentForm_136, PaymentForm_143


class PaymentFormConverter(ConverterBase):
    base = PaymentForm
    old = [PaymentForm_136, PaymentForm_143]
    layers = [136, 143]

    @staticmethod
    def from_136(obj: PaymentForm_136) -> PaymentForm:
        data = obj.to_dict()
        data["title"] = ""
        data["description"] = ""
        if data["saved_credentials"] is not None:
            data["saved_credentials"] = [data["saved_credentials"]]
        return PaymentForm(**data)

    @staticmethod
    def to_136(obj: PaymentForm) -> PaymentForm_136:
        data = obj.to_dict()
        del data["photo"]
        del data["additional_methods"]
        del data["title"]
        del data["description"]
        if data["saved_credentials"]:
            data["saved_credentials"] = data["saved_credentials"][0]
        return PaymentForm_136(**data)

    @staticmethod
    def from_143(obj: PaymentForm_143) -> PaymentForm:
        data = obj.to_dict()
        if data["saved_credentials"] is not None:
            data["saved_credentials"] = [data["saved_credentials"]]
        return PaymentForm(**data)

    @staticmethod
    def to_143(obj: PaymentForm) -> PaymentForm_143:
        data = obj.to_dict()
        del data["additional_methods"]
        if data["saved_credentials"]:
            data["saved_credentials"] = data["saved_credentials"][0]
        return PaymentForm_143(**data)
