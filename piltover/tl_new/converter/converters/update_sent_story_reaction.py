from piltover.tl_new import PeerUser
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import UpdateSentStoryReaction, UpdateSentStoryReaction_161


class UpdateSentStoryReactionConverter(ConverterBase):
    base = UpdateSentStoryReaction
    old = [UpdateSentStoryReaction_161]
    layers = [161]

    @staticmethod
    def from_161(obj: UpdateSentStoryReaction_161) -> UpdateSentStoryReaction:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return UpdateSentStoryReaction(**data)

    @staticmethod
    def to_161(obj: UpdateSentStoryReaction) -> UpdateSentStoryReaction_161:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return UpdateSentStoryReaction_161(**data)
