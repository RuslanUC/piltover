from piltover.tl_new.types import MessageActionGiftPremium, MessageActionGiftPremium_144
from piltover.tl_new.converter import ConverterBase


class MessageActionGiftPremiumConverter(ConverterBase):
    base = MessageActionGiftPremium
    old = [MessageActionGiftPremium_144]
    layers = [144]

    @staticmethod
    def from_144(obj: MessageActionGiftPremium_144) -> MessageActionGiftPremium:
        data = obj.to_dict()
        return MessageActionGiftPremium(**data)

    @staticmethod
    def to_144(obj: MessageActionGiftPremium) -> MessageActionGiftPremium_144:
        data = obj.to_dict()
        del data["flags"]
        del data["crypto_amount"]
        del data["crypto_currency"]
        return MessageActionGiftPremium_144(**data)

