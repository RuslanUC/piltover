from piltover.tl import ReactionEmoji
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import GetMessageReactionsList, GetMessageReactionsList_136


class GetMessageReactionsListConverter(ConverterBase):
    base = GetMessageReactionsList
    old = [GetMessageReactionsList_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetMessageReactionsList_136) -> GetMessageReactionsList:
        data = obj.to_dict()
        if data["reaction"] is not None:
            data["reaction"] = ReactionEmoji(emoticon=obj.reaction)
        return GetMessageReactionsList(**data)

    @staticmethod
    def to_136(obj: GetMessageReactionsList) -> GetMessageReactionsList_136:
        data = obj.to_dict()
        data["reaction"] = obj.reaction.emoticon if isinstance(obj.reaction, ReactionEmoji) else None
        return GetMessageReactionsList_136(**data)
