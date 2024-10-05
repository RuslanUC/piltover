from piltover.tl import PeerUser
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import SendReaction, SendReaction_161


class SendReactionConverter(ConverterBase):
    base = SendReaction
    old = [SendReaction_161]
    layers = [161]

    @staticmethod
    def from_161(obj: SendReaction_161) -> SendReaction:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return SendReaction(**data)

    @staticmethod
    def to_161(obj: SendReaction) -> SendReaction_161:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return SendReaction_161(**data)
