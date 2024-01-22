from piltover.tl_new.functions.messages import SetDefaultReaction, SetDefaultReaction_136
from piltover.tl_new.converter import ConverterBase


class SetDefaultReactionConverter(ConverterBase):
    base = SetDefaultReaction
    old = [SetDefaultReaction_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SetDefaultReaction_136) -> SetDefaultReaction:
        data = obj.to_dict()
        assert False, "type of field 'reaction' changed (string -> Reaction)"  # TODO: type changed
        return SetDefaultReaction(**data)

    @staticmethod
    def to_136(obj: SetDefaultReaction) -> SetDefaultReaction_136:
        data = obj.to_dict()
        assert False, "type of field 'reaction' changed (Reaction -> string)"  # TODO: type changed
        return SetDefaultReaction_136(**data)

