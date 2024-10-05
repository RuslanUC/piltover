from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import SendMultiMedia, SendMultiMedia_136, SendMultiMedia_148


class SendMultiMediaConverter(ConverterBase):
    base = SendMultiMedia
    old = [SendMultiMedia_136, SendMultiMedia_148]
    layers = [136, 148]

    @staticmethod
    def from_136(obj: SendMultiMedia_136) -> SendMultiMedia:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return SendMultiMedia(**data)

    @staticmethod
    def to_136(obj: SendMultiMedia) -> SendMultiMedia_136:
        data = obj.to_dict()
        del data["reply_to"]
        del data["update_stickersets_order"]
        del data["invert_media"]
        return SendMultiMedia_136(**data)

    @staticmethod
    def from_148(obj: SendMultiMedia_148) -> SendMultiMedia:
        data = obj.to_dict()
        del data["top_msg_id"]
        del data["reply_to_msg_id"]
        return SendMultiMedia(**data)

    @staticmethod
    def to_148(obj: SendMultiMedia) -> SendMultiMedia_148:
        data = obj.to_dict()
        del data["reply_to"]
        del data["invert_media"]
        return SendMultiMedia_148(**data)
