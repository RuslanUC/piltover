from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import Message_136, Message, Message_170, Message_174, Message_176


class MessageDowngradeTo136(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 136
    TARGET_TYPE = Message_136
    REMOVE_FIELDS = {
        "invert_media", "offline", "from_boosts_applied", "saved_peer_id", "via_business_bot_id",
        "quick_reply_shortcut_id"
    }


class MessageDowngradeTo170(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 170
    TARGET_TYPE = Message_170
    REMOVE_FIELDS = {"offline", "from_boosts_applied", "via_business_bot_id", "quick_reply_shortcut_id"}


class MessageDowngradeTo174(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 174
    TARGET_TYPE = Message_174
    REMOVE_FIELDS = {"offline", "via_business_bot_id", "quick_reply_shortcut_id"}


class MessageDowngradeTo176(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 176
    TARGET_TYPE = Message_176
    REMOVE_FIELDS = {"offline", "via_business_bot_id"}


class MessageDontDowngrade(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 177
    TARGET_TYPE = Message
    REMOVE_FIELDS = set()
