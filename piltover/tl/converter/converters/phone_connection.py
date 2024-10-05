from piltover.tl.converter import ConverterBase
from piltover.tl.types import PhoneConnection, PhoneConnection_136


class PhoneConnectionConverter(ConverterBase):
    base = PhoneConnection
    old = [PhoneConnection_136]
    layers = [136]

    @staticmethod
    def from_136(obj: PhoneConnection_136) -> PhoneConnection:
        data = obj.to_dict()
        return PhoneConnection(**data)

    @staticmethod
    def to_136(obj: PhoneConnection) -> PhoneConnection_136:
        data = obj.to_dict()
        del data["tcp"]
        del data["flags"]
        return PhoneConnection_136(**data)
