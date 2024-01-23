from piltover.tl_new import PeerUser
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import WebPageAttributeStory, WebPageAttributeStory_160


class WebPageAttributeStoryConverter(ConverterBase):
    base = WebPageAttributeStory
    old = [WebPageAttributeStory_160]
    layers = [160]

    @staticmethod
    def from_160(obj: WebPageAttributeStory_160) -> WebPageAttributeStory:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return WebPageAttributeStory(**data)

    @staticmethod
    def to_160(obj: WebPageAttributeStory) -> WebPageAttributeStory_160:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return WebPageAttributeStory_160(**data)
