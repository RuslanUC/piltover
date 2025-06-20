from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChatInvite, ChatInvite_136, ChatInvite_166, ChatInvite_186


class ChatInviteDowngradeTo136(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_LAYER = 136
    TARGET_TYPE = ChatInvite_136
    REMOVE_FIELDS = {
        "verified", "scam", "fake", "color", "can_refulfill_subscription", "subscription_pricing",
        "subscription_form_id", "bot_verification",
    }


class ChatInviteDowngradeTo166(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_LAYER = 166
    TARGET_TYPE = ChatInvite_166
    REMOVE_FIELDS = {"can_refulfill_subscription", "subscription_pricing", "subscription_form_id", "bot_verification"}


class ChatInviteDowngradeTo186(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_LAYER = 186
    TARGET_TYPE = ChatInvite_186
    REMOVE_FIELDS = {"bot_verification"}


class ChatInviteDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_LAYER = 201
    TARGET_TYPE = ChatInvite
    REMOVE_FIELDS = set()
