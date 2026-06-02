from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChatInviteExported, ChatInviteExported_134, ChatInviteExported_133


class ChatInviteExportedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = ChatInviteExported
    TARGET_TYPE = ChatInviteExported_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"subscription_expired", "subscription_pricing", "request_needed", "requested", "title"}


class ChatInviteExportedDowngradeTo134(AutoDowngrader):
    BASE_TYPE = ChatInviteExported
    TARGET_TYPE = ChatInviteExported_134
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"subscription_expired", "subscription_pricing"}


class ChatInviteExportedDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChatInviteExported
    TARGET_TYPE = ChatInviteExported
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
