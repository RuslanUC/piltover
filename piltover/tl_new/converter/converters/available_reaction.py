from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import AvailableReaction, AvailableReaction_136


class AvailableReactionConverter(ConverterBase):
    base = AvailableReaction
    old = [AvailableReaction_136]
    layers = [136]

    @staticmethod
    def from_136(obj: AvailableReaction_136) -> AvailableReaction:
        data = obj.to_dict()
        return AvailableReaction(**data)

    @staticmethod
    def to_136(obj: AvailableReaction) -> AvailableReaction_136:
        data = obj.to_dict()
        del data["premium"]
        del data["around_animation"]
        del data["center_icon"]
        return AvailableReaction_136(**data)
