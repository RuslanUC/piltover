from piltover.tl_new.types import SponsoredMessage, SponsoredMessage_136, SponsoredMessage_155, SponsoredMessage_160
from piltover.tl_new.converter import ConverterBase


class SponsoredMessageConverter(ConverterBase):
    base = SponsoredMessage
    old = [SponsoredMessage_136, SponsoredMessage_155, SponsoredMessage_160]
    layers = [136, 155, 160]

    @staticmethod
    def from_136(obj: SponsoredMessage_136) -> SponsoredMessage:
        data = obj.to_dict()
        return SponsoredMessage(**data)

    @staticmethod
    def to_136(obj: SponsoredMessage) -> SponsoredMessage_136:
        data = obj.to_dict()
        del data["webpage"]
        del data["show_peer_photo"]
        del data["sponsor_info"]
        del data["button_text"]
        del data["additional_info"]
        del data["app"]
        return SponsoredMessage_136(**data)

    @staticmethod
    def from_155(obj: SponsoredMessage_155) -> SponsoredMessage:
        data = obj.to_dict()
        return SponsoredMessage(**data)

    @staticmethod
    def to_155(obj: SponsoredMessage) -> SponsoredMessage_155:
        data = obj.to_dict()
        del data["webpage"]
        del data["button_text"]
        del data["app"]
        return SponsoredMessage_155(**data)

    @staticmethod
    def from_160(obj: SponsoredMessage_160) -> SponsoredMessage:
        data = obj.to_dict()
        return SponsoredMessage(**data)

    @staticmethod
    def to_160(obj: SponsoredMessage) -> SponsoredMessage_160:
        data = obj.to_dict()
        del data["button_text"]
        del data["app"]
        return SponsoredMessage_160(**data)

