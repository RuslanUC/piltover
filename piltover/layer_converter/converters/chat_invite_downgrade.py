from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChatInvite, ChatInvite_136


class ChatInviteDowngradeTo136(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_LAYER = 136
    TARGET_TYPE = ChatInvite_136
    REMOVE_FIELDS = {"verified", "scam", "fake", "color"}


class ChatInviteDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChatInvite
    TARGET_LAYER = 177
    TARGET_TYPE = ChatInvite
    REMOVE_FIELDS = set()
