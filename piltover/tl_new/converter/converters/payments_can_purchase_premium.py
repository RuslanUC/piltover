from piltover.tl_new.functions.payments import CanPurchasePremium, CanPurchasePremium_143
from piltover.tl_new.converter import ConverterBase


class CanPurchasePremiumConverter(ConverterBase):
    base = CanPurchasePremium
    old = [CanPurchasePremium_143]
    layers = [143]

    @staticmethod
    def from_143(obj: CanPurchasePremium_143) -> CanPurchasePremium:
        data = obj.to_dict()
        assert False, "required field 'purpose' added in base tl object"  # TODO: add field
        return CanPurchasePremium(**data)

    @staticmethod
    def to_143(obj: CanPurchasePremium) -> CanPurchasePremium_143:
        data = obj.to_dict()
        del data["purpose"]
        return CanPurchasePremium_143(**data)

