from piltover.tl_new.functions.payments import ValidateRequestedInfo, ValidateRequestedInfo_136
from piltover.tl_new.converter import ConverterBase


class ValidateRequestedInfoConverter(ConverterBase):
    base = ValidateRequestedInfo
    old = [ValidateRequestedInfo_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ValidateRequestedInfo_136) -> ValidateRequestedInfo:
        data = obj.to_dict()
        assert False, "required field 'invoice' added in base tl object"  # TODO: add field
        del data["msg_id"]
        del data["peer"]
        return ValidateRequestedInfo(**data)

    @staticmethod
    def to_136(obj: ValidateRequestedInfo) -> ValidateRequestedInfo_136:
        data = obj.to_dict()
        del data["invoice"]
        assert False, "required field 'msg_id' deleted in base tl object"  # TODO: delete field
        assert False, "required field 'peer' deleted in base tl object"  # TODO: delete field
        return ValidateRequestedInfo_136(**data)

