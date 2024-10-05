from piltover.tl.converter import ConverterBase
from piltover.tl.types import PremiumSubscriptionOption, PremiumSubscriptionOption_145


class PremiumSubscriptionOptionConverter(ConverterBase):
    base = PremiumSubscriptionOption
    old = [PremiumSubscriptionOption_145]
    layers = [145]

    @staticmethod
    def from_145(obj: PremiumSubscriptionOption_145) -> PremiumSubscriptionOption:
        data = obj.to_dict()
        return PremiumSubscriptionOption(**data)

    @staticmethod
    def to_145(obj: PremiumSubscriptionOption) -> PremiumSubscriptionOption_145:
        data = obj.to_dict()
        del data["transaction"]
        return PremiumSubscriptionOption_145(**data)
