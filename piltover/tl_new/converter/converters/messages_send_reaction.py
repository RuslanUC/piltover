from piltover.tl_new import ReactionEmoji
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.messages import SendReaction, SendReaction_136


class SendReactionConverter(ConverterBase):
    base = SendReaction
    old = [SendReaction_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SendReaction_136) -> SendReaction:
        data = obj.to_dict()
        if data["reaction"] is not None:
            data["reaction"] = [ReactionEmoji(emoticon=obj.reaction)]
        return SendReaction(**data)

    @staticmethod
    def to_136(obj: SendReaction) -> SendReaction_136:
        data = obj.to_dict()
        del data["add_to_recent"]
        if data["reaction"] is not None:
            data["reaction"] = obj.reaction[0] if obj.reaction else ""
        return SendReaction_136(**data)
