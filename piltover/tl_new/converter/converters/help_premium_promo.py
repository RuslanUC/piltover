from piltover.tl_new import PremiumSubscriptionOption
from piltover.tl_new.types.help import PremiumPromo, PremiumPromo_143
from piltover.tl_new.converter import ConverterBase


class PremiumPromoConverter(ConverterBase):
    base = PremiumPromo
    old = [PremiumPromo_143]
    layers = [143]

    @staticmethod
    def from_143(obj: PremiumPromo_143) -> PremiumPromo:
        data = obj.to_dict()
        data["period_options"] = [
            PremiumSubscriptionOption(months=1, amount=obj.monthly_amount, currency=obj.currency, bot_url="")
        ]
        del data["monthly_amount"]
        del data["currency"]
        return PremiumPromo(**data)

    @staticmethod
    def to_143(obj: PremiumPromo) -> PremiumPromo_143:
        data = obj.to_dict()
        del data["period_options"]
        data["monthly_amount"] = obj.period_options[0].amount
        data["currency"] = obj.period_options[0].currency
        return PremiumPromo_143(**data)

