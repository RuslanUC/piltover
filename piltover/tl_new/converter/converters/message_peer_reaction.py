from piltover.tl_new import ReactionEmoji
from piltover.tl_new.types import MessagePeerReaction, MessagePeerReaction_138, MessagePeerReaction_145
from piltover.tl_new.converter import ConverterBase


class MessagePeerReactionConverter(ConverterBase):
    base = MessagePeerReaction
    old = [MessagePeerReaction_138, MessagePeerReaction_145]
    layers = [138, 145]

    @staticmethod
    def from_138(obj: MessagePeerReaction_138) -> MessagePeerReaction:
        data = obj.to_dict()
        data["date"] = 0
        data["reaction"] = ReactionEmoji(emoticon=obj.reaction)
        return MessagePeerReaction(**data)

    @staticmethod
    def to_138(obj: MessagePeerReaction) -> MessagePeerReaction_138:
        data = obj.to_dict()
        del data["my"]
        del data["date"]
        data["reaction"] = obj.reaction.emoticon if isinstance(obj.reaction, ReactionEmoji) else ""
        return MessagePeerReaction_138(**data)

    @staticmethod
    def from_145(obj: MessagePeerReaction_145) -> MessagePeerReaction:
        data = obj.to_dict()
        data["date"] = 0
        return MessagePeerReaction(**data)

    @staticmethod
    def to_145(obj: MessagePeerReaction) -> MessagePeerReaction_145:
        data = obj.to_dict()
        del data["my"]
        del data["date"]
        return MessagePeerReaction_145(**data)

