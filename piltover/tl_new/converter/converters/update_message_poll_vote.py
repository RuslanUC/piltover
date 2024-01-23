from piltover.tl_new import PeerUser
from piltover.tl_new.types import UpdateMessagePollVote, UpdateMessagePollVote_136
from piltover.tl_new.converter import ConverterBase


class UpdateMessagePollVoteConverter(ConverterBase):
    base = UpdateMessagePollVote
    old = [UpdateMessagePollVote_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdateMessagePollVote_136) -> UpdateMessagePollVote:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return UpdateMessagePollVote(**data)

    @staticmethod
    def to_136(obj: UpdateMessagePollVote) -> UpdateMessagePollVote_136:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return UpdateMessagePollVote_136(**data)
