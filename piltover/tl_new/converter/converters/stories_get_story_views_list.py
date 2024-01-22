from piltover.tl_new.functions.stories import GetStoryViewsList, GetStoryViewsList_160, GetStoryViewsList_161
from piltover.tl_new.converter import ConverterBase


class GetStoryViewsListConverter(ConverterBase):
    base = GetStoryViewsList
    old = [GetStoryViewsList_160, GetStoryViewsList_161]
    layers = [160, 161]

    @staticmethod
    def from_160(obj: GetStoryViewsList_160) -> GetStoryViewsList:
        data = obj.to_dict()
        assert False, "required field 'offset' added in base tl object"  # TODO: add field
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
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
        assert False, "required field 'offset_date' deleted in base tl object"  # TODO: delete field
        assert False, "required field 'offset_id' deleted in base tl object"  # TODO: delete field
        return GetStoryViewsList_160(**data)

    @staticmethod
    def from_161(obj: GetStoryViewsList_161) -> GetStoryViewsList:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        return GetStoryViewsList(**data)

    @staticmethod
    def to_161(obj: GetStoryViewsList) -> GetStoryViewsList_161:
        data = obj.to_dict()
        del data["peer"]
        return GetStoryViewsList_161(**data)

