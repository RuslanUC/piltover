from copy import copy

from piltover.layer_converter.converters.base import BaseDowngrader
from piltover.tl import Message_136, Message, Message_170, Message_174, Message_176


class MessageDowngradeTo136(BaseDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: Message) -> Message_136:
        kwargs = from_obj.to_dict()
        del kwargs["invert_media"]
        del kwargs["offline"]
        del kwargs["from_boosts_applied"]
        del kwargs["saved_peer_id"]
        del kwargs["via_business_bot_id"]
        del kwargs["quick_reply_shortcut_id"]

        return Message_136(**kwargs)


class MessageDowngradeTo170(BaseDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 170

    @classmethod
    def downgrade(cls, from_obj: Message) -> Message_170:
        kwargs = from_obj.to_dict()
        del kwargs["offline"]
        del kwargs["from_boosts_applied"]
        del kwargs["via_business_bot_id"]
        del kwargs["quick_reply_shortcut_id"]

        return Message_170(**kwargs)


class MessageDowngradeTo174(BaseDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 174

    @classmethod
    def downgrade(cls, from_obj: Message) -> Message_174:
        kwargs = from_obj.to_dict()
        del kwargs["offline"]
        del kwargs["via_business_bot_id"]
        del kwargs["quick_reply_shortcut_id"]

        return Message_174(**kwargs)


class MessageDowngradeTo176(BaseDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 176

    @classmethod
    def downgrade(cls, from_obj: Message) -> Message_176:
        kwargs = from_obj.to_dict()
        del kwargs["offline"]
        del kwargs["via_business_bot_id"]

        return Message_176(**kwargs)


class MessageDontDowngrade(BaseDowngrader):
    BASE_TYPE = Message
    TARGET_LAYER = 177

    @classmethod
    def downgrade(cls, from_obj: Message) -> Message:
        return copy(from_obj)
