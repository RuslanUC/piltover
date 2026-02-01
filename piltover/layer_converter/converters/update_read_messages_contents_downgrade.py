from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import UpdateReadMessagesContents, UpdateReadMessagesContents_133


class UpdateReadMessagesContentsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = UpdateReadMessagesContents
    TARGET_TYPE = UpdateReadMessagesContents_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"date"}


class UpdateReadMessagesContentsDontDowngrade163(AutoDowngrader):
    BASE_TYPE = UpdateReadMessagesContents
    TARGET_TYPE = UpdateReadMessagesContents
    TARGET_LAYER = 163
    REMOVE_FIELDS = set()


class UpdateReadMessagesContentsDontDowngrade(AutoDowngrader):
    BASE_TYPE = UpdateReadMessagesContents
    TARGET_TYPE = UpdateReadMessagesContents
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
