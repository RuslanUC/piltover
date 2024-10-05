from piltover.tl import ReactionEmoji
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import SetDefaultReaction, SetDefaultReaction_136


class SetDefaultReactionConverter(ConverterBase):
    base = SetDefaultReaction
    old = [SetDefaultReaction_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SetDefaultReaction_136) -> SetDefaultReaction:
        data = obj.to_dict()
        data["reaction"] = ReactionEmoji(emoticon=obj.reaction)
        return SetDefaultReaction(**data)

    @staticmethod
    def to_136(obj: SetDefaultReaction) -> SetDefaultReaction_136:
        data = obj.to_dict()
        data["reaction"] = obj.reaction.emoticon
        return SetDefaultReaction_136(**data)
