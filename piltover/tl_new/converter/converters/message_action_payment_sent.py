from piltover.tl_new.types import MessageActionPaymentSent, MessageActionPaymentSent_136
from piltover.tl_new.converter import ConverterBase


class MessageActionPaymentSentConverter(ConverterBase):
    base = MessageActionPaymentSent
    old = [MessageActionPaymentSent_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageActionPaymentSent_136) -> MessageActionPaymentSent:
        data = obj.to_dict()
        return MessageActionPaymentSent(**data)

    @staticmethod
    def to_136(obj: MessageActionPaymentSent) -> MessageActionPaymentSent_136:
        data = obj.to_dict()
        del data["recurring_used"]
        del data["invoice_slug"]
        del data["recurring_init"]
        del data["flags"]
        return MessageActionPaymentSent_136(**data)

