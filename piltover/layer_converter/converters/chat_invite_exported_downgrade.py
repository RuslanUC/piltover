from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChatInviteExported, ChatInviteExported_134, ChatInviteExported_133


class ChatInviteExportedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = ChatInviteExported
    TARGET_LAYER = 133
    TARGET_TYPE = ChatInviteExported_133
    REMOVE_FIELDS = {"subscription_expired", "subscription_pricing", "request_needed", "requested", "title"}


class ChatInviteExportedDowngradeTo134(AutoDowngrader):
    BASE_TYPE = ChatInviteExported
    TARGET_LAYER = 134
    TARGET_TYPE = ChatInviteExported_134
    REMOVE_FIELDS = {"subscription_expired", "subscription_pricing"}


class ChatInviteExportedDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChatInviteExported
    TARGET_LAYER = 201
    TARGET_TYPE = ChatInviteExported
    REMOVE_FIELDS = set()
