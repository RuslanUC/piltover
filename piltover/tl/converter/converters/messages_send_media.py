from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import SendMedia, SendMedia_136, SendMedia_148


class SendMediaConverter(ConverterBase):
    base = SendMedia
    old = [SendMedia_136, SendMedia_148]
    layers = [136, 148]

    @staticmethod
    def from_136(obj: SendMedia_136) -> SendMedia:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return SendMedia(**data)

    @staticmethod
    def to_136(obj: SendMedia) -> SendMedia_136:
        data = obj.to_dict()
        del data["reply_to"]
        del data["update_stickersets_order"]
        del data["invert_media"]
        return SendMedia_136(**data)

    @staticmethod
    def from_148(obj: SendMedia_148) -> SendMedia:
        data = obj.to_dict()
        del data["top_msg_id"]
        del data["reply_to_msg_id"]
        return SendMedia(**data)

    @staticmethod
    def to_148(obj: SendMedia) -> SendMedia_148:
        data = obj.to_dict()
        del data["reply_to"]
        del data["invert_media"]
        return SendMedia_148(**data)
