from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import UpdateDeleteScheduledMessages, UpdateDeleteScheduledMessages_133


class UpdateDeleteScheduledMessagesDowngradeTo133(AutoDowngrader):
    BASE_TYPE = UpdateDeleteScheduledMessages
    TARGET_TYPE = UpdateDeleteScheduledMessages_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"sent_messages"}


class UpdateDeleteScheduledMessagesDontDowngrade(AutoDowngrader):
    BASE_TYPE = UpdateDeleteScheduledMessages
    TARGET_TYPE = UpdateDeleteScheduledMessages
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
