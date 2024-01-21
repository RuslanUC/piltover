from piltover.tl_new import TLObject
from piltover.tl_new.converter import ConverterBase
from piltover.utils.utils import SingletonMeta


class ConverterManager(metaclass=SingletonMeta):
    def __init__(self):
        self._converters: dict[type[TLObject], type[ConverterBase]] = {}

    def register(self, conv: type[ConverterBase]) -> None:
        self._converters[conv.base] = conv
        for old in conv.old:
            self._converters[old] = conv

    def upgrade(self, obj: TLObject) -> TLObject:
        if type(obj) not in self._converters:
            return obj

        name = obj.tlname().split("_")
        if not name[-1].isdigit():
            return obj

        layer = int(name[-1])
        conv = self._converters[type(obj)]
        layer = max(lr for lr in conv.layers if lr <= layer)
        func = getattr(conv, f"from_{layer}")

        return func(obj)

    def downgrade(self, obj: TLObject, layer: int) -> TLObject:
        if type(obj) not in self._converters:
            return obj

        conv = self._converters[type(obj)]
        layer = max(lr for lr in conv.layers if lr <= layer)
        func = getattr(conv, f"to_{layer}")

        return func(obj)


"""
from piltover.tl_new.converter.converter_manager import ConverterManager
from piltover.tl_new.converter.converters.user_ import UserConverter
from piltover.tl_new import User, User_136

ConverterManager().register(UserConverter)

u136 = User_136(flags=0, id=123, bot=True, fake=True, phone="123123")
u = ConverterManager().upgrade(u136)
u160 = ConverterManager().downgrade(u, 160)
"""
