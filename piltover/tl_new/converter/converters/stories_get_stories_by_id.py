from piltover.tl_new.functions.stories import GetStoriesByID, GetStoriesByID_160
from piltover.tl_new.converter import ConverterBase


class GetStoriesByIDConverter(ConverterBase):
    base = GetStoriesByID
    old = [GetStoriesByID_160]
    layers = [160]

    @staticmethod
    def from_160(obj: GetStoriesByID_160) -> GetStoriesByID:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        del data["user_id"]
        return GetStoriesByID(**data)

    @staticmethod
    def to_160(obj: GetStoriesByID) -> GetStoriesByID_160:
        data = obj.to_dict()
        del data["peer"]
        assert False, "required field 'user_id' deleted in base tl object"  # TODO: delete field
        return GetStoriesByID_160(**data)

