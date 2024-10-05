from piltover.tl import InputPeerUser, InputUser
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import GetStoriesByID, GetStoriesByID_160


class GetStoriesByIDConverter(ConverterBase):
    base = GetStoriesByID
    old = [GetStoriesByID_160]
    layers = [160]

    @staticmethod
    def from_160(obj: GetStoriesByID_160) -> GetStoriesByID:
        data = obj.to_dict()
        data["peer"] = InputPeerUser(user_id=obj.user_id, access_hash=obj.user_id.access_hash)
        del data["user_id"]
        return GetStoriesByID(**data)

    @staticmethod
    def to_160(obj: GetStoriesByID) -> GetStoriesByID_160:
        data = obj.to_dict()
        del data["peer"]
        data["peer"] = InputUser(user_id=obj.peer.user_id, access_hash=obj.peer.access_hash)
        return GetStoriesByID_160(**data)
