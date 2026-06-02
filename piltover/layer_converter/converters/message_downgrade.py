from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import Message_136, Message_133, Message, Message_170, Message_174, Message_176, Message_177, \
    Message_181, Message_196


class MessageDowngradeTo133(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "invert_media", "offline", "from_boosts_applied", "saved_peer_id", "via_business_bot_id",
        "quick_reply_shortcut_id", "video_processing_pending", "effect", "factcheck", "report_delivery_until_date",
        "paid_message_stars", "reactions",
    }


class MessageDowngradeTo136(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message_136
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "invert_media", "offline", "from_boosts_applied", "saved_peer_id", "via_business_bot_id",
        "quick_reply_shortcut_id", "video_processing_pending", "effect", "factcheck", "report_delivery_until_date",
        "paid_message_stars",
    }


class MessageDowngradeTo170(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message_170
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "offline", "from_boosts_applied", "via_business_bot_id", "quick_reply_shortcut_id", "video_processing_pending",
        "effect", "factcheck", "report_delivery_until_date", "paid_message_stars",
    }


class MessageDowngradeTo174(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message_174
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "offline", "via_business_bot_id", "quick_reply_shortcut_id", "video_processing_pending", "effect", "factcheck",
        "report_delivery_until_date", "paid_message_stars",
    }


class MessageDowngradeTo176(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message_176
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "offline", "via_business_bot_id", "video_processing_pending", "effect", "factcheck",
        "report_delivery_until_date", "paid_message_stars",
    }


class MessageDowngradeTo177(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message_177
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "video_processing_pending", "effect", "factcheck", "report_delivery_until_date", "paid_message_stars",
    }


class MessageDowngradeTo181(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message_181
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"video_processing_pending", "report_delivery_until_date", "paid_message_stars"}


class MessageDowngradeTo196(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message_196
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"paid_message_stars"}


class MessageDontDowngrade(AutoDowngrader):
    BASE_TYPE = Message
    TARGET_TYPE = Message
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
