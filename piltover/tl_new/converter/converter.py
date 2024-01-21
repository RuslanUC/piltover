from piltover.tl_new import TLObject


class ConverterBase:
    base: type[TLObject]
    old: list[type[TLObject]]
