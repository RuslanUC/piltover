from piltover.tl import InputReplyToMessage
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import SendScreenshotNotification, SendScreenshotNotification_136


class SendScreenshotNotificationConverter(ConverterBase):
    base = SendScreenshotNotification
    old = [SendScreenshotNotification_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SendScreenshotNotification_136) -> SendScreenshotNotification:
        data = obj.to_dict()
        data["reply_to"] = InputReplyToMessage(reply_to_msg_id=obj.reply_to_msg_id)
        del data["reply_to_msg_id"]
        return SendScreenshotNotification(**data)

    @staticmethod
    def to_136(obj: SendScreenshotNotification) -> SendScreenshotNotification_136:
        data = obj.to_dict()
        del data["reply_to"]
        data["reply_to_msg_id"] = obj.reply_to.reply_to_msg_id
        return SendScreenshotNotification_136(**data)
