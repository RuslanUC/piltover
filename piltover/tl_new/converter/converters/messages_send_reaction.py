from piltover.tl_new.functions.messages import SendReaction, SendReaction_136
from piltover.tl_new.converter import ConverterBase


class SendReactionConverter(ConverterBase):
    base = SendReaction
    old = [SendReaction_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SendReaction_136) -> SendReaction:
        data = obj.to_dict()
        assert False, "type of field 'reaction' changed (flags.0?string -> flags.0?Vector<Reaction>)"  # TODO: type changed
        return SendReaction(**data)

    @staticmethod
    def to_136(obj: SendReaction) -> SendReaction_136:
        data = obj.to_dict()
        del data["add_to_recent"]
        assert False, "type of field 'reaction' changed (flags.0?Vector<Reaction> -> flags.0?string)"  # TODO: type changed
        return SendReaction_136(**data)

