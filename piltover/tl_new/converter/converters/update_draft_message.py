from piltover.tl_new.types import UpdateDraftMessage, UpdateDraftMessage_136
from piltover.tl_new.converter import ConverterBase


class UpdateDraftMessageConverter(ConverterBase):
    base = UpdateDraftMessage
    old = [UpdateDraftMessage_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdateDraftMessage_136) -> UpdateDraftMessage:
        data = obj.to_dict()
        return UpdateDraftMessage(**data)

    @staticmethod
    def to_136(obj: UpdateDraftMessage) -> UpdateDraftMessage_136:
        data = obj.to_dict()
        del data["flags"]
        del data["top_msg_id"]
        return UpdateDraftMessage_136(**data)

