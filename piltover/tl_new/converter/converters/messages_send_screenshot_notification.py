from piltover.tl_new.functions.messages import SendScreenshotNotification, SendScreenshotNotification_136
from piltover.tl_new.converter import ConverterBase


class SendScreenshotNotificationConverter(ConverterBase):
    base = SendScreenshotNotification
    old = [SendScreenshotNotification_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SendScreenshotNotification_136) -> SendScreenshotNotification:
        data = obj.to_dict()
        assert False, "required field 'reply_to' added in base tl object"  # TODO: add field
        del data["reply_to_msg_id"]
        return SendScreenshotNotification(**data)

    @staticmethod
    def to_136(obj: SendScreenshotNotification) -> SendScreenshotNotification_136:
        data = obj.to_dict()
        del data["reply_to"]
        assert False, "required field 'reply_to_msg_id' deleted in base tl object"  # TODO: delete field
        return SendScreenshotNotification_136(**data)

