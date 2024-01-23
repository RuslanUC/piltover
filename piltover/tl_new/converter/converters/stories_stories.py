from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types.stories import Stories, Stories_160


class StoriesConverter(ConverterBase):
    base = Stories
    old = [Stories_160]
    layers = [160]

    @staticmethod
    def from_160(obj: Stories_160) -> Stories:
        data = obj.to_dict()
        data["chats"] = []
        return Stories(**data)

    @staticmethod
    def to_160(obj: Stories) -> Stories_160:
        data = obj.to_dict()
        del data["chats"]
        return Stories_160(**data)
