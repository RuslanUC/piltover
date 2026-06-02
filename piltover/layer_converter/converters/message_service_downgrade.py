from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageService, MessageService_133


class MessageServiceDowngradeTo133(AutoDowngrader):
    BASE_TYPE = MessageService
    TARGET_TYPE = MessageService_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"reactions_are_possible", "reactions"}


class MessageServiceDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageService
    TARGET_TYPE = MessageService
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
