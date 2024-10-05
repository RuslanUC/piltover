from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import CreateChat, CreateChat_136


class CreateChatConverter(ConverterBase):
    base = CreateChat
    old = [CreateChat_136]
    layers = [136]

    @staticmethod
    def from_136(obj: CreateChat_136) -> CreateChat:
        data = obj.to_dict()
        return CreateChat(**data)

    @staticmethod
    def to_136(obj: CreateChat) -> CreateChat_136:
        data = obj.to_dict()
        del data["flags"]
        del data["ttl_period"]
        return CreateChat_136(**data)
