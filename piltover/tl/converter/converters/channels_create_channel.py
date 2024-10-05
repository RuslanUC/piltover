from piltover.tl.converter import ConverterBase
from piltover.tl.functions.channels import CreateChannel, CreateChannel_136


class CreateChannelConverter(ConverterBase):
    base = CreateChannel
    old = [CreateChannel_136]
    layers = [136]

    @staticmethod
    def from_136(obj: CreateChannel_136) -> CreateChannel:
        data = obj.to_dict()
        return CreateChannel(**data)

    @staticmethod
    def to_136(obj: CreateChannel) -> CreateChannel_136:
        data = obj.to_dict()
        del data["ttl_period"]
        del data["forum"]
        return CreateChannel_136(**data)
