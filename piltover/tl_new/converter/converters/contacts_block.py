from piltover.tl_new.functions.contacts import Block, Block_136
from piltover.tl_new.converter import ConverterBase


class BlockConverter(ConverterBase):
    base = Block
    old = [Block_136]
    layers = [136]

    @staticmethod
    def from_136(obj: Block_136) -> Block:
        data = obj.to_dict()
        return Block(**data)

    @staticmethod
    def to_136(obj: Block) -> Block_136:
        data = obj.to_dict()
        del data["my_stories_from"]
        del data["flags"]
        return Block_136(**data)

