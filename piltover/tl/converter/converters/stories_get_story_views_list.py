from piltover.tl import InputPeerEmpty
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import GetStoryViewsList, GetStoryViewsList_160, GetStoryViewsList_161


class GetStoryViewsListConverter(ConverterBase):
    base = GetStoryViewsList
    old = [GetStoryViewsList_160, GetStoryViewsList_161]
    layers = [160, 161]

    @staticmethod
    def from_160(obj: GetStoryViewsList_160) -> GetStoryViewsList:
        data = obj.to_dict()
        data["offset"] = ""
        data["peer"] = InputPeerEmpty()
        del data["offset_date"]
        del data["offset_id"]
        return GetStoryViewsList(**data)

    @staticmethod
    def to_160(obj: GetStoryViewsList) -> GetStoryViewsList_160:
        data = obj.to_dict()
        del data["just_contacts"]
        del data["reactions_first"]
        del data["offset"]
        del data["flags"]
        del data["q"]
        del data["peer"]
        data["offset_date"] = 0
        data["offset_id"] = 0
        return GetStoryViewsList_160(**data)

    @staticmethod
    def from_161(obj: GetStoryViewsList_161) -> GetStoryViewsList:
        data = obj.to_dict()
        data["peer"] = InputPeerEmpty()
        return GetStoryViewsList(**data)

    @staticmethod
    def to_161(obj: GetStoryViewsList) -> GetStoryViewsList_161:
        data = obj.to_dict()
        del data["peer"]
        return GetStoryViewsList_161(**data)
