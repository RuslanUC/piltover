from piltover.tl_new.types import ReactionCount, ReactionCount_136
from piltover.tl_new.converter import ConverterBase


class ReactionCountConverter(ConverterBase):
    base = ReactionCount
    old = [ReactionCount_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ReactionCount_136) -> ReactionCount:
        data = obj.to_dict()
        del data["chosen"]
        assert False, "type of field 'reaction' changed (string -> Reaction)"  # TODO: type changed
        return ReactionCount(**data)

    @staticmethod
    def to_136(obj: ReactionCount) -> ReactionCount_136:
        data = obj.to_dict()
        del data["chosen_order"]
        assert False, "type of field 'reaction' changed (Reaction -> string)"  # TODO: type changed
        return ReactionCount_136(**data)

