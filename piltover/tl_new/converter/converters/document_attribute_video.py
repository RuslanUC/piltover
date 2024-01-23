from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import DocumentAttributeVideo, DocumentAttributeVideo_136


class DocumentAttributeVideoConverter(ConverterBase):
    base = DocumentAttributeVideo
    old = [DocumentAttributeVideo_136]
    layers = [136]

    @staticmethod
    def from_136(obj: DocumentAttributeVideo_136) -> DocumentAttributeVideo:
        data = obj.to_dict()
        data["duration"] = float(data["duration"])
        return DocumentAttributeVideo(**data)

    @staticmethod
    def to_136(obj: DocumentAttributeVideo) -> DocumentAttributeVideo_136:
        data = obj.to_dict()
        del data["preload_prefix_size"]
        del data["nosound"]
        data["duration"] = int(data["duration"])
        return DocumentAttributeVideo_136(**data)
