from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types.auth import SentCodeTypeEmailCode, SentCodeTypeEmailCode_145


class SentCodeTypeEmailCodeConverter(ConverterBase):
    base = SentCodeTypeEmailCode
    old = [SentCodeTypeEmailCode_145]
    layers = [145]

    @staticmethod
    def from_145(obj: SentCodeTypeEmailCode_145) -> SentCodeTypeEmailCode:
        data = obj.to_dict()
        del data["next_phone_login_date"]
        return SentCodeTypeEmailCode(**data)

    @staticmethod
    def to_145(obj: SentCodeTypeEmailCode) -> SentCodeTypeEmailCode_145:
        data = obj.to_dict()
        del data["reset_available_period"]
        del data["reset_pending_date"]
        return SentCodeTypeEmailCode_145(**data)
