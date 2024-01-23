from piltover.tl_new import InputPeerUser, InputUser
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.stories import ExportStoryLink, ExportStoryLink_160


class ExportStoryLinkConverter(ConverterBase):
    base = ExportStoryLink
    old = [ExportStoryLink_160]
    layers = [160]

    @staticmethod
    def from_160(obj: ExportStoryLink_160) -> ExportStoryLink:
        data = obj.to_dict()
        data["peer"] = InputPeerUser(user_id=obj.user_id, access_hash=obj.user_id.access_hash)
        del data["user_id"]
        return ExportStoryLink(**data)

    @staticmethod
    def to_160(obj: ExportStoryLink) -> ExportStoryLink_160:
        data = obj.to_dict()
        del data["peer"]
        data["peer"] = InputUser(user_id=obj.peer.user_id, access_hash=obj.peer.access_hash)
        return ExportStoryLink_160(**data)
