from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageReactions, MessageReactions_136, MessageReactions_138


class MessageReactionsDowngradeTo136(AutoDowngrader):
    BASE_TYPE = MessageReactions
    TARGET_TYPE = MessageReactions_136
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"reactions_as_tags", "recent_reactions", "top_reactors"}


class MessageReactionsDowngradeTo138(AutoDowngrader):
    BASE_TYPE = MessageReactions
    TARGET_TYPE = MessageReactions_138
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"reactions_as_tags", "top_reactors"}


class MessageReactionsDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageReactions
    TARGET_TYPE = MessageReactions
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
