from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageService, MessageService_133


class MessageServiceDowngradeTo133(AutoDowngrader):
    BASE_TYPE = MessageService
    TARGET_LAYER = 133
    TARGET_TYPE = MessageService_133
    REMOVE_FIELDS = {"reactions_are_possible", "reactions"}


class MessageServiceDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageService
    TARGET_LAYER = 201
    TARGET_TYPE = MessageService
    REMOVE_FIELDS = set()
