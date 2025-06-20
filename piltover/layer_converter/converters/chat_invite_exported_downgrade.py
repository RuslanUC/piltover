from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChatInviteExported, ChatInviteExported_136


class ChatInviteExportedDowngradeTo136(AutoDowngrader):
    BASE_TYPE = ChatInviteExported
    TARGET_LAYER = 136
    TARGET_TYPE = ChatInviteExported_136
    REMOVE_FIELDS = {"subscription_expired", "subscription_pricing"}


class ChatInviteExportedDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChatInviteExported
    TARGET_LAYER = 201
    TARGET_TYPE = ChatInviteExported
    REMOVE_FIELDS = set()
