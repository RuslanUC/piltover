from piltover.tl import PeerUser
from piltover.tl.converter import ConverterBase
from piltover.tl.types import MessageMediaStory, MessageMediaStory_160


class MessageMediaStoryConverter(ConverterBase):
    base = MessageMediaStory
    old = [MessageMediaStory_160]
    layers = [160]

    @staticmethod
    def from_160(obj: MessageMediaStory_160) -> MessageMediaStory:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return MessageMediaStory(**data)

    @staticmethod
    def to_160(obj: MessageMediaStory) -> MessageMediaStory_160:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return MessageMediaStory_160(**data)
