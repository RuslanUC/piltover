from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChatFull, ChatFull_136, ChatFull_145, ChatFull_133, ChatFull_134


class ChatFullDowngradeTo133(AutoDowngrader):
    BASE_TYPE = ChatFull
    TARGET_TYPE = ChatFull_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "translations_disabled", "reactions_limit", "requests_pending", "recent_requesters", "available_reactions",
    }


class ChatFullDowngradeTo134(AutoDowngrader):
    BASE_TYPE = ChatFull
    TARGET_TYPE = ChatFull_134
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"translations_disabled", "reactions_limit", "available_reactions"}


class ChatFullDowngradeTo136(AutoDowngrader):
    BASE_TYPE = ChatFull
    TARGET_TYPE = ChatFull_136
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"translations_disabled", "reactions_limit"}


class ChatFullDowngradeTo145(AutoDowngrader):
    BASE_TYPE = ChatFull
    TARGET_TYPE = ChatFull_145
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"reactions_limit"}


class ChatFullDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChatFull
    TARGET_TYPE = ChatFull
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
