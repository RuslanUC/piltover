from piltover.tl_new.functions.stories import ExportStoryLink, ExportStoryLink_160
from piltover.tl_new.converter import ConverterBase


class ExportStoryLinkConverter(ConverterBase):
    base = ExportStoryLink
    old = [ExportStoryLink_160]
    layers = [160]

    @staticmethod
    def from_160(obj: ExportStoryLink_160) -> ExportStoryLink:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        del data["user_id"]
        return ExportStoryLink(**data)

    @staticmethod
    def to_160(obj: ExportStoryLink) -> ExportStoryLink_160:
        data = obj.to_dict()
        del data["peer"]
        assert False, "required field 'user_id' deleted in base tl object"  # TODO: delete field
        return ExportStoryLink_160(**data)

