from piltover.tl import PeerUser
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import Report, Report_160


class ReportConverter(ConverterBase):
    base = Report
    old = [Report_160]
    layers = [160]

    @staticmethod
    def from_160(obj: Report_160) -> Report:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id.user_id)
        del data["user_id"]
        return Report(**data)

    @staticmethod
    def to_160(obj: Report) -> Report_160:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return Report_160(**data)
