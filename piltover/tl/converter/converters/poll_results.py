from piltover.tl import PeerUser
from piltover.tl.converter import ConverterBase
from piltover.tl.types import PollResults, PollResults_136


class PollResultsConverter(ConverterBase):
    base = PollResults
    old = [PollResults_136]
    layers = [136]

    @staticmethod
    def from_136(obj: PollResults_136) -> PollResults:
        data = obj.to_dict()
        if data["recent_voters"] is not None:
            data["recent_voters"] = [PeerUser(user_id=uid) for uid in obj.recent_voters]
        return PollResults(**data)

    @staticmethod
    def to_136(obj: PollResults) -> PollResults_136:
        data = obj.to_dict()
        if data["recent_voters"] is not None:
            data["recent_voters"] = [peer.user_id for peer in obj.recent_voters if isinstance(peer, PeerUser)]
        return PollResults_136(**data)
