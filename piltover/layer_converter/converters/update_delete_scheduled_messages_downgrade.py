from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import UpdateDeleteScheduledMessages, UpdateDeleteScheduledMessages_133


class UpdateDeleteScheduledMessagesDowngradeTo133(AutoDowngrader):
    BASE_TYPE = UpdateDeleteScheduledMessages
    TARGET_LAYER = 133
    TARGET_TYPE = UpdateDeleteScheduledMessages_133
    REMOVE_FIELDS = {"sent_messages"}


class UpdateDeleteScheduledMessagesDontDowngrade192(AutoDowngrader):
    BASE_TYPE = UpdateDeleteScheduledMessages
    TARGET_LAYER = 192
    TARGET_TYPE = UpdateDeleteScheduledMessages
    REMOVE_FIELDS = set()


class UpdateDeleteScheduledMessagesDontDowngrade(AutoDowngrader):
    BASE_TYPE = UpdateDeleteScheduledMessages
    TARGET_LAYER = 201
    TARGET_TYPE = UpdateDeleteScheduledMessages
    REMOVE_FIELDS = set()
