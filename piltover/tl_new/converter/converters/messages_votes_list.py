from piltover.tl_new.types.messages import VotesList, VotesList_136
from piltover.tl_new.converter import ConverterBase


class VotesListConverter(ConverterBase):
    base = VotesList
    old = [VotesList_136]
    layers = [136]

    @staticmethod
    def from_136(obj: VotesList_136) -> VotesList:
        data = obj.to_dict()
        assert False, "required field 'chats' added in base tl object"  # TODO: add field
        assert False, "type of field 'votes' changed (Vector<MessageUserVote> -> Vector<MessagePeerVote>)"  # TODO: type changed
        return VotesList(**data)

    @staticmethod
    def to_136(obj: VotesList) -> VotesList_136:
        data = obj.to_dict()
        del data["chats"]
        assert False, "type of field 'votes' changed (Vector<MessagePeerVote> -> Vector<MessageUserVote>)"  # TODO: type changed
        return VotesList_136(**data)

