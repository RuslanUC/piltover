from piltover.tl_new.types import PollResults, PollResults_136
from piltover.tl_new.converter import ConverterBase


class PollResultsConverter(ConverterBase):
    base = PollResults
    old = [PollResults_136]
    layers = [136]

    @staticmethod
    def from_136(obj: PollResults_136) -> PollResults:
        data = obj.to_dict()
        assert False, "type of field 'recent_voters' changed (flags.3?Vector<long> -> flags.3?Vector<Peer>)"  # TODO: type changed
        return PollResults(**data)

    @staticmethod
    def to_136(obj: PollResults) -> PollResults_136:
        data = obj.to_dict()
        assert False, "type of field 'recent_voters' changed (flags.3?Vector<Peer> -> flags.3?Vector<long>)"  # TODO: type changed
        return PollResults_136(**data)

