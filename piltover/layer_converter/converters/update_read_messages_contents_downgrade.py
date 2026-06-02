from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import UpdateReadMessagesContents, UpdateReadMessagesContents_133


class UpdateReadMessagesContentsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = UpdateReadMessagesContents
    TARGET_TYPE = UpdateReadMessagesContents_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"date"}


class UpdateReadMessagesContentsDontDowngrade(AutoDowngrader):
    BASE_TYPE = UpdateReadMessagesContents
    TARGET_TYPE = UpdateReadMessagesContents
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
