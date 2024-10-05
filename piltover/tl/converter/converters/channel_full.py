from piltover.tl import ChatReactionsSome, ReactionEmoji
from piltover.tl.converter import ConverterBase
from piltover.tl.types import ChannelFull, ChannelFull_136, ChannelFull_140, ChannelFull_145


class ChannelFullConverter(ConverterBase):
    base = ChannelFull
    old = [ChannelFull_136, ChannelFull_140, ChannelFull_145]
    layers = [136, 140, 145]

    @staticmethod
    def from_136(obj: ChannelFull_136) -> ChannelFull:
        data = obj.to_dict()
        if data["available_reactions"] is not None:
            data["new_value"] = ChatReactionsSome(
                reactions=[ReactionEmoji(emoticon=reaction) for reaction in obj.available_reactions]
            )
        return ChannelFull(**data)

    @staticmethod
    def to_136(obj: ChannelFull) -> ChannelFull_136:
        data = obj.to_dict()
        del data["antispam"]
        del data["translations_disabled"]
        del data["flags2"]
        del data["participants_hidden"]
        del data["stories"]
        del data["can_delete_channel"]
        del data["stories_pinned_available"]
        del data["view_forum_as_messages"]
        if isinstance(obj.available_reactions, ChatReactionsSome):
            data["new_value"] = [
                reaction.emoticon for reaction in obj.available_reactions.reactions
                if isinstance(reaction, ReactionEmoji)
            ]
        return ChannelFull_136(**data)

    @staticmethod
    def from_140(obj: ChannelFull_140) -> ChannelFull:
        data = obj.to_dict()
        if data["available_reactions"] is not None:
            data["new_value"] = ChatReactionsSome(
                reactions=[ReactionEmoji(emoticon=reaction) for reaction in obj.available_reactions]
            )
        return ChannelFull(**data)

    @staticmethod
    def to_140(obj: ChannelFull) -> ChannelFull_140:
        data = obj.to_dict()
        del data["antispam"]
        del data["translations_disabled"]
        del data["participants_hidden"]
        del data["stories"]
        del data["stories_pinned_available"]
        del data["view_forum_as_messages"]
        if isinstance(obj.available_reactions, ChatReactionsSome):
            data["new_value"] = [
                reaction.emoticon for reaction in obj.available_reactions.reactions
                if isinstance(reaction, ReactionEmoji)
            ]
        return ChannelFull_140(**data)

    @staticmethod
    def from_145(obj: ChannelFull_145) -> ChannelFull:
        data = obj.to_dict()
        return ChannelFull(**data)

    @staticmethod
    def to_145(obj: ChannelFull) -> ChannelFull_145:
        data = obj.to_dict()
        del data["antispam"]
        del data["translations_disabled"]
        del data["participants_hidden"]
        del data["stories"]
        del data["stories_pinned_available"]
        del data["view_forum_as_messages"]
        return ChannelFull_145(**data)
