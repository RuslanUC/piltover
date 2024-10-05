from piltover.tl import ChatReactionsSome, ReactionEmoji
from piltover.tl.converter import ConverterBase
from piltover.tl.types import ChannelAdminLogEventActionChangeAvailableReactions, \
    ChannelAdminLogEventActionChangeAvailableReactions_136


class ChannelAdminLogEventActionChangeAvailableReactionsConverter(ConverterBase):
    base = ChannelAdminLogEventActionChangeAvailableReactions
    old = [ChannelAdminLogEventActionChangeAvailableReactions_136]
    layers = [136]

    @staticmethod
    def from_136(
            obj: ChannelAdminLogEventActionChangeAvailableReactions_136) -> ChannelAdminLogEventActionChangeAvailableReactions:
        data = obj.to_dict()
        data["new_value"] = ChatReactionsSome(
            reactions=[ReactionEmoji(emoticon=reaction) for reaction in obj.new_value]
        )
        data["prev_value"] = ChatReactionsSome(
            reactions=[ReactionEmoji(emoticon=reaction) for reaction in obj.prev_value]
        )
        return ChannelAdminLogEventActionChangeAvailableReactions(**data)

    @staticmethod
    def to_136(
            obj: ChannelAdminLogEventActionChangeAvailableReactions) -> ChannelAdminLogEventActionChangeAvailableReactions_136:
        data = obj.to_dict()
        data["new_value"] = []
        data["prev_value"] = []
        if isinstance(obj.new_value, ChatReactionsSome):
            data["new_value"] = [
                reaction.emoticon for reaction in obj.new_value.reactions if isinstance(reaction, ReactionEmoji)
            ]
        if isinstance(obj.prev_value, ChatReactionsSome):
            data["prev_value"] = [
                reaction.emoticon for reaction in obj.prev_value.reactions if isinstance(reaction, ReactionEmoji)
            ]
        return ChannelAdminLogEventActionChangeAvailableReactions_136(**data)
