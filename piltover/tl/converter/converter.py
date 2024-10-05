from .. import TLObject


class ConverterBase:
    base: type[TLObject]
    old: list[type[TLObject]]
    layers: list[int] | set[int]
