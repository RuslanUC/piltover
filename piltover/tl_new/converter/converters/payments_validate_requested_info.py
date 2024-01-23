from piltover.tl_new import InputInvoiceMessage, InputPeerEmpty
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.payments import ValidateRequestedInfo, ValidateRequestedInfo_136


class ValidateRequestedInfoConverter(ConverterBase):
    base = ValidateRequestedInfo
    old = [ValidateRequestedInfo_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ValidateRequestedInfo_136) -> ValidateRequestedInfo:
        data = obj.to_dict()
        data["invoice"] = InputInvoiceMessage(peer=obj.peer, msg_id=obj.msg_id)
        del data["msg_id"]
        del data["peer"]
        return ValidateRequestedInfo(**data)

    @staticmethod
    def to_136(obj: ValidateRequestedInfo) -> ValidateRequestedInfo_136:
        data = obj.to_dict()
        del data["invoice"]
        data["msg_id"] = obj.invoice.msg_id
        data["peer"] = InputPeerEmpty()
        return ValidateRequestedInfo_136(**data)
