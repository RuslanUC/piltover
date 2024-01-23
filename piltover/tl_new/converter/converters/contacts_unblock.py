from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.contacts import Unblock, Unblock_136


class UnblockConverter(ConverterBase):
    base = Unblock
    old = [Unblock_136]
    layers = [136]

    @staticmethod
    def from_136(obj: Unblock_136) -> Unblock:
        data = obj.to_dict()
        return Unblock(**data)

    @staticmethod
    def to_136(obj: Unblock) -> Unblock_136:
        data = obj.to_dict()
        del data["my_stories_from"]
        del data["flags"]
        return Unblock_136(**data)
