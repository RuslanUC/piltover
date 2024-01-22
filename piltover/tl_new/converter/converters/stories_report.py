from piltover.tl_new import PeerUser
from piltover.tl_new.functions.stories import Report, Report_160
from piltover.tl_new.converter import ConverterBase


class ReportConverter(ConverterBase):
    base = Report
    old = [Report_160]
    layers = [160]

    @staticmethod
    def from_160(obj: Report_160) -> Report:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return Report(**data)

    @staticmethod
    def to_160(obj: Report) -> Report_160:
        data = obj.to_dict()
        del data["peer"]
        assert False, "required field 'user_id' deleted in base tl object"  # TODO: delete field
        return Report_160(**data)

