from piltover.tl_new import MessagePeerVote, MessagePeerVoteInputOption, MessagePeerVoteMultiple, MessageUserVote_136, \
    MessageUserVoteInputOption_136, MessageUserVoteMultiple_136, PeerUser
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types.messages import VotesList, VotesList_136


class VotesListConverter(ConverterBase):
    base = VotesList
    old = [VotesList_136]
    layers = [136]

    @staticmethod
    def from_136(obj: VotesList_136) -> VotesList:
        data = obj.to_dict()
        data["chats"] = []
        data["votes"] = []
        for vote in obj.votes:
            if isinstance(vote, MessageUserVote_136):
                data["votes"].append(MessagePeerVote(
                    peer=PeerUser(user_id=vote.user_id), option=vote.option, date=vote.date
                ))
            elif isinstance(vote, MessageUserVoteInputOption_136):
                data["votes"].append(MessagePeerVoteInputOption(
                    peer=PeerUser(user_id=vote.user_id), date=vote.date
                ))
            elif isinstance(vote, MessageUserVoteMultiple_136):
                data["votes"].append(MessagePeerVoteMultiple(
                    peer=PeerUser(user_id=vote.user_id), options=vote.options, date=vote.date
                ))
        return VotesList(**data)

    @staticmethod
    def to_136(obj: VotesList) -> VotesList_136:
        data = obj.to_dict()
        del data["chats"]
        data["votes"] = []
        for vote in obj.votes:
            if not isinstance(vote.peer, PeerUser):
                continue
            if isinstance(vote, MessagePeerVote):
                data["votes"].append(MessageUserVote_136(
                    user_id=vote.peer.user_id, option=vote.option, date=vote.date
                ))
            elif isinstance(vote, MessagePeerVoteInputOption):
                data["votes"].append(MessageUserVoteInputOption_136(
                    user_id=vote.peer.user_id, date=vote.date
                ))
            elif isinstance(vote, MessagePeerVoteMultiple):
                data["votes"].append(MessageUserVoteMultiple_136(
                    user_id=vote.peer.user_id, options=vote.options, date=vote.date
                ))
        return VotesList_136(**data)
