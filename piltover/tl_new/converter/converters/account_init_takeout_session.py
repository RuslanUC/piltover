from piltover.tl_new.functions.account import InitTakeoutSession, InitTakeoutSession_136
from piltover.tl_new.converter import ConverterBase


class InitTakeoutSessionConverter(ConverterBase):
    base = InitTakeoutSession
    old = [InitTakeoutSession_136]
    layers = [136]

    @staticmethod
    def from_136(obj: InitTakeoutSession_136) -> InitTakeoutSession:
        data = obj.to_dict()
        return InitTakeoutSession(**data)

    @staticmethod
    def to_136(obj: InitTakeoutSession) -> InitTakeoutSession_136:
        data = obj.to_dict()
        return InitTakeoutSession_136(**data)

