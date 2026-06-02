from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChatInvite, ChatInvite_134, ChatInvite_166, ChatInvite_186, ChatInvite_133


class ChatInviteDowngradeTo133(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_TYPE = ChatInvite_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "verified", "scam", "fake", "color", "can_refulfill_subscription", "subscription_pricing",
        "subscription_form_id", "bot_verification", "request_needed", "about",
    }


class ChatInviteDowngradeTo134(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_TYPE = ChatInvite_134
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "verified", "scam", "fake", "color", "can_refulfill_subscription", "subscription_pricing",
        "subscription_form_id", "bot_verification",
    }


class ChatInviteDowngradeTo166(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_TYPE = ChatInvite_166
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"can_refulfill_subscription", "subscription_pricing", "subscription_form_id", "bot_verification"}


class ChatInviteDowngradeTo186(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_TYPE = ChatInvite_186
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"bot_verification"}


class ChatInviteDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_TYPE = ChatInvite
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
