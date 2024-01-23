from piltover.tl_new import ReactionEmoji
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import ReactionCount, ReactionCount_136


class ReactionCountConverter(ConverterBase):
    base = ReactionCount
    old = [ReactionCount_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ReactionCount_136) -> ReactionCount:
        data = obj.to_dict()
        del data["chosen"]
        data["reaction"] = ReactionEmoji(emoticon=obj.reaction)
        return ReactionCount(**data)

    @staticmethod
    def to_136(obj: ReactionCount) -> ReactionCount_136:
        data = obj.to_dict()
        del data["chosen_order"]
        data["reaction"] = obj.reaction.emoticon
        return ReactionCount_136(**data)
