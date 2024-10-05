from piltover.tl import InputStorePaymentPremiumSubscription
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.payments import CanPurchasePremium, CanPurchasePremium_143


class CanPurchasePremiumConverter(ConverterBase):
    base = CanPurchasePremium
    old = [CanPurchasePremium_143]
    layers = [143]

    @staticmethod
    def from_143(obj: CanPurchasePremium_143) -> CanPurchasePremium:
        data = obj.to_dict()
        data["purpose"] = InputStorePaymentPremiumSubscription()
        return CanPurchasePremium(**data)

    @staticmethod
    def to_143(obj: CanPurchasePremium) -> CanPurchasePremium_143:
        data = obj.to_dict()
        del data["purpose"]
        return CanPurchasePremium_143(**data)
