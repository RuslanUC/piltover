from piltover.tl_new import PeerUser
from piltover.tl_new.functions.stories import SendReaction, SendReaction_161
from piltover.tl_new.converter import ConverterBase


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
        assert False, "required field 'user_id' deleted in base tl object"  # TODO: delete field
        return SendReaction_161(**data)

